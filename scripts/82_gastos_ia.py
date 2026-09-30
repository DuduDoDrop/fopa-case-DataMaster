# -*- coding: utf-8 -*-
"""
Os gastos com IA — o que foi COBRADO — gravados para a home do site (db/045).

    python scripts/82_gastos_ia.py                     lê a fatura da OpenAI e da Anthropic e grava
    python scripts/82_gastos_ia.py --so-mostrar        só mostra, não grava
    python scripts/82_gastos_ia.py --desde 2026-09-22  a partir de quando somar (padrão: 22/09/2026)
    python scripts/82_gastos_ia.py --jev-painel 17.78 [--jev-desde 2026-09-21]
                                                       grava a leitura do painel da TypeSafe (Usage → Spend)

POR QUE EXISTE
  A home do painel soma os gastos do Jev, do Claude e do GPT, com o custo lido nas APIs Admin (26/09).
  A fatura é a única resposta que vale para "quanto custou"
  (o mesmo argumento do 32_custo_real.py): a estimativa do pipeline depende da tabela de preço, a fatura não.

DE ONDE VEM CADA NÚMERO
  OpenAI     /v1/organization/costs (OPENAI_ADMIN_KEY). Dólares.
  Anthropic  /v1/organizations/cost_report (ANTHROPIC_ADMIN_KEY). O `amount` vem em CENTAVOS, texto decimal.
  Jev        a TypeSafe não tem API de faturamento (docs.typesafe.ai/api: só `usage` por chamada). Vale a leitura
             do painel dela, informada no --jev-painel; a home soma o que o sistema mediu depois
             (sinais_jev.usd). Sem leitura do painel, a home mostra só o medido.
  As duas Admin APIs dão a organização INTEIRA: se a mesma conta servir a outro projeto, entra aqui também. Por isso
  o padrão começa em 22/09/2026, o primeiro commit do FOPA: na Anthropic há US$ 0,84 de 01 a 08/09 (sonnet-4-6 e
  4-5, de outro trabalho), e de 22/09 em diante só modelos que o FOPA usou; a OpenAI tem um projeto só.
  Ler a fatura não é chamada de modelo: não gasta token nem entra no teto de US$ 5.

Nenhuma chave é impressa.
"""
from __future__ import annotations

import argparse
import json
import os
import sys
import urllib.error
import urllib.parse
import urllib.request
from collections import defaultdict
from datetime import date, datetime, timedelta, timezone

for _f in (sys.stdout, sys.stderr):
    try:
        _f.reconfigure(encoding="utf-8", errors="replace")
    except (AttributeError, ValueError):
        pass

RAIZ = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(RAIZ, "scripts"))
sys.path.insert(0, os.path.join(RAIZ, "n8n"))

import cliente  # noqa: E402
import psycopg  # noqa: E402
from fopa import segredos  # noqa: E402

DESDE_PADRAO = "2026-09-22"          # o primeiro commit do FOPA


def _pegar(url: str, cabecalhos: dict) -> dict:
    req = urllib.request.Request(url, headers=cabecalhos)
    with urllib.request.urlopen(req, timeout=40) as r:
        return json.loads(r.read().decode("utf-8"))


def openai(chave: str, desde: date) -> tuple[float, dict]:
    """Soma /v1/organization/costs dia a dia, página a página."""
    ini = int(datetime(desde.year, desde.month, desde.day, tzinfo=timezone.utc).timestamp())
    por_dia: dict[str, float] = defaultdict(float)
    por_item: dict[str, float] = defaultdict(float)
    pagina = None
    while True:
        q = {"start_time": ini, "bucket_width": "1d", "limit": 180, "group_by": "line_item"}
        if pagina:
            q["page"] = pagina
        d = _pegar("https://api.openai.com/v1/organization/costs?" + urllib.parse.urlencode(q),
                   {"Authorization": "Bearer %s" % chave})
        for b in d.get("data", []):
            dia = datetime.fromtimestamp(b["start_time"], timezone.utc).date().isoformat()
            for r in b.get("results", []):
                v = float((r.get("amount") or {}).get("value") or 0.0)
                por_dia[dia] += v
                por_item[r.get("line_item") or "(sem item)"] += v
        pagina = d.get("next_page") if d.get("has_more") else None
        if not pagina:
            break
    return sum(por_dia.values()), {"por_dia": _arredondar(por_dia), "por_item": _arredondar(por_item)}


def anthropic(chave: str, desde: date) -> tuple[float, dict]:
    """Soma /v1/organizations/cost_report (centavos, texto decimal) dia a dia, página a página."""
    fim = datetime.now(timezone.utc).date() + timedelta(days=1)
    por_dia: dict[str, float] = defaultdict(float)
    por_item: dict[str, float] = defaultdict(float)
    pagina = None
    while True:
        q = [("starting_at", "%sT00:00:00Z" % desde.isoformat()), ("ending_at", "%sT00:00:00Z" % fim.isoformat()),
             ("group_by[]", "description"), ("limit", 31)]
        if pagina:
            q.append(("page", pagina))
        d = _pegar("https://api.anthropic.com/v1/organizations/cost_report?" + urllib.parse.urlencode(q),
                   {"x-api-key": chave, "anthropic-version": "2023-06-01"})
        for b in d.get("data", []):
            dia = (b.get("starting_at") or "")[:10]
            for r in b.get("results", []):
                v = float(r.get("amount") or 0) / 100.0            # centavos → dólares
                por_dia[dia] += v
                por_item[r.get("model") or r.get("description") or "(sem descrição)"] += v
        pagina = d.get("next_page") if d.get("has_more") else None
        if not pagina:
            break
    return sum(por_dia.values()), {"por_dia": _arredondar(por_dia), "por_item": _arredondar(por_item)}


def _arredondar(d: dict[str, float]) -> dict[str, float]:
    return {k: round(v, 4) for k, v in sorted(d.items()) if round(v, 4)}


def _url_banco() -> str:
    return "postgresql://postgres:%s@127.0.0.1:5433/fopa" % cliente.ler_env()["POSTGRES_PASSWORD"]


def gravar(provedor: str, usd: float, desde: date, fonte: str, detalhe: dict | None) -> None:
    with psycopg.connect(_url_banco()) as conn:
        conn.execute("INSERT INTO gastos_ia (provedor, usd, desde, fonte, detalhe) VALUES (%s, %s, %s, %s, %s)",
                     (provedor, round(usd, 4), desde, fonte, json.dumps(detalhe) if detalhe else None))


def main() -> int:
    ap = argparse.ArgumentParser(description="Gastos com IA (fatura) para a home do site")
    ap.add_argument("--desde", default=DESDE_PADRAO, help="AAAA-MM-DD (padrão %s)" % DESDE_PADRAO)
    ap.add_argument("--so-mostrar", action="store_true", help="não grava no banco")
    ap.add_argument("--jev-painel", type=float, help="o Spend do painel da TypeSafe, em US$")
    ap.add_argument("--jev-desde", default="2026-09-21", help="o início do período do painel (padrão 2026-09-21)")
    args = ap.parse_args()
    segredos.carregar()

    if args.jev_painel is not None:
        desde = date.fromisoformat(args.jev_desde)
        print("Jev (painel da TypeSafe): US$ %.2f desde %s" % (args.jev_painel, desde.strftime("%d/%m/%Y")))
        if not args.so_mostrar:
            gravar("jev", args.jev_painel, desde, "painel", None)
            print("  gravado; a home soma o que o sistema medir depois de agora")
        return 0

    desde = date.fromisoformat(args.desde)
    falhou = 0
    for nome, rotulo, var, ler in (("openai", "GPT (OpenAI)", "OPENAI_ADMIN_KEY", openai),
                                   ("anthropic", "Claude (Anthropic)", "ANTHROPIC_ADMIN_KEY", anthropic)):
        chave = segredos.obter(var)
        if not chave:
            print("%s: %s não está no .env — sem leitura" % (rotulo, var))
            falhou += 1
            continue
        try:
            total, detalhe = ler(chave, desde)
        except urllib.error.HTTPError as e:
            corpo = e.read().decode("utf-8", "replace")[:300]
            print("%s: HTTP %d na Admin API — %s" % (rotulo, e.code, corpo))
            falhou += 1
            continue
        except urllib.error.URLError as e:
            print("%s: sem conexão com a Admin API (%s)" % (rotulo, e.reason))
            falhou += 1
            continue
        print("%s: US$ %.4f desde %s" % (rotulo, total, desde.strftime("%d/%m/%Y")))
        for item, v in sorted(detalhe["por_item"].items(), key=lambda x: -x[1])[:6]:
            print("    US$ %8.4f  %s" % (v, item))
        if not args.so_mostrar:
            gravar(nome, total, desde, "admin-api", detalhe)
    return 1 if falhou else 0


if __name__ == "__main__":
    raise SystemExit(main())
