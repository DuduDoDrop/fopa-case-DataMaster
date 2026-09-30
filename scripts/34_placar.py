# -*- coding: utf-8 -*-
"""
Placar completo de uma licitação: acurácia, ancoragem, tempo e custo REAL.

    python 34_placar.py "<pasta>"
    python 34_placar.py "<pasta>" --md          saída em Markdown, para o vault

POR QUE UM GERADOR, E NÃO UMA TABELA ESCRITA
  Porque a tabela tem cinco fontes e cada uma muda por conta própria: as
  auditorias em disco, o gabarito, o harness, a fatura da OpenAI (que atualiza
  em segundos) e a da Anthropic (que atrasa um dia). Uma tabela escrita à mão
  fica desatualizada na próxima execução — e desatualizada em silêncio, que é o
  modo de falha que este projeto persegue.

O CUSTO VEM DA FATURA, NÃO DA ESTIMATIVA
  E as duas aparecem lado a lado quando ambas existem, de propósito: a diferença
  entre elas é um número útil. Foi assim que se descobriu que o preço unitário
  configurado (do `gpt-5.6-sol`) errava por 2× quando aplicado ao `gpt-6-astra`.

ASSIMETRIA ENTRE OS PROVEDORES, MEDIDA
  A API de custos da OpenAI publica em segundos; a da Anthropic leva ~1 dia.
  Onde a fatura ainda não fechou, a coluna diz "pendente" — nunca zero, que
  seria lido como grátis.
"""
from __future__ import annotations

import argparse
import glob
import importlib.util
import io
import json
import os
import sys
import time
import urllib.request
from collections import defaultdict

for _f in (sys.stdout, sys.stderr):
    try:
        _f.reconfigure(encoding="utf-8", errors="replace")
    except (AttributeError, ValueError):
        pass

AQUI = os.path.dirname(os.path.abspath(__file__))
RAIZ = os.path.dirname(AQUI)
sys.path.insert(0, AQUI)

from fopa import modelos, segredos                                # noqa: E402

AMOSTRAS = os.path.join(RAIZ, "amostras")
SAIDAS = os.path.join(RAIZ, "saidas")


def _acuracia_mod():
    """`15_acuracia.py` começa com dígito: não dá para importar pelo nome."""
    spec = importlib.util.spec_from_file_location(
        "acuracia", os.path.join(AQUI, "15_acuracia.py"))
    m = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(m)
    return m


# ------------------------------------------------------------------ faturas
def fatura_openai(horas: int = 48) -> dict[str, float]:
    chave = segredos.obter("OPENAI_ADMIN_KEY")
    if not chave:
        return {}
    url = ("https://api.openai.com/v1/organization/costs?start_time=%d"
           "&limit=31&group_by[]=line_item" % (int(time.time()) - 3600 * horas))
    try:
        req = urllib.request.Request(url, headers={"Authorization": "Bearer %s" % chave})
        with urllib.request.urlopen(req, timeout=40) as r:
            d = json.loads(r.read().decode("utf-8"))
    except Exception:                                              # noqa: BLE001
        return {}
    por: dict[str, float] = defaultdict(float)
    for b in d.get("data", []):
        for x in b.get("results", []):
            m = (x.get("line_item") or "").split(",")[0].strip()
            por[m] += (x.get("amount") or {}).get("value") or 0.0
    return dict(por)


def uso_openai(horas: int = 48) -> dict[str, dict]:
    """Tokens por modelo na janela — o denominador que diz se a fatura é isolável."""
    chave = segredos.obter("OPENAI_ADMIN_KEY")
    if not chave:
        return {}
    url = ("https://api.openai.com/v1/organization/usage/completions?start_time=%d"
           "&bucket_width=1d&group_by=model&limit=31"
           % (int(time.time()) - 3600 * horas))
    try:
        req = urllib.request.Request(url, headers={"Authorization": "Bearer %s" % chave})
        with urllib.request.urlopen(req, timeout=40) as r:
            d = json.loads(r.read().decode("utf-8"))
    except Exception:                                              # noqa: BLE001
        return {}
    por: dict[str, dict] = defaultdict(lambda: defaultdict(int))
    for b in d.get("data", []):
        for x in b.get("results", []):
            m = x.get("model") or "?"
            for c in ("input_tokens", "output_tokens", "num_model_requests"):
                por[m][c] += x.get(c) or 0
    return {k: dict(v) for k, v in por.items()}


# Mapeia "Claude Opus 5.5 - Input Tokens" -> "claude-opus-5-5"
def _id_anthropic(descricao: str) -> str:
    d = (descricao or "").split(" - ")[0].strip().lower()
    return d.replace("claude ", "claude-").replace(" ", "-").replace(".", "-")


def fatura_anthropic(dias: int = 3) -> dict[str, float]:
    chave = segredos.obter("ANTHROPIC_ADMIN_KEY")
    if not chave:
        return {}
    ini = time.strftime("%Y-%m-%dT00:00:00Z",
                        time.gmtime(time.time() - 86400 * dias))
    url = ("https://api.anthropic.com/v1/organizations/cost_report"
           "?starting_at=%s&limit=%d&group_by[]=description" % (ini, dias + 1))
    try:
        req = urllib.request.Request(
            url, headers={"x-api-key": chave, "anthropic-version": "2023-06-01"})
        with urllib.request.urlopen(req, timeout=40) as r:
            d = json.loads(r.read().decode("utf-8"))
    except Exception:                                              # noqa: BLE001
        return {}
    por: dict[str, float] = defaultdict(float)
    for b in d.get("data", []):
        for x in b.get("results", []):
            # O `amount` vem em CENTAVOS, apesar de `currency: USD`. Confirmado
            # batendo contra os tokens: fator exatamente 100x em quatro linhas.
            por[_id_anthropic(x.get("description"))] += \
                float(x.get("amount") or 0) / 100.0
    return dict(por)


# ------------------------------------------------------------------ execuções
def execucoes(nome: str) -> list[dict]:
    """Toda auditoria desta licitação, venha de onde vier."""
    achadas = []
    padroes = [os.path.join(SAIDAS, nome, "auditoria.json"),
               os.path.join(SAIDAS, "_varredura_%s" % nome, "*", "auditoria.json"),
               os.path.join(SAIDAS, "_openai_*", "auditoria.json")]
    for p in padroes:
        for f in sorted(glob.glob(p)):
            try:
                d = json.load(io.open(f, encoding="utf-8"))
            except (ValueError, OSError):
                continue
            if d.get("licitacao") != nome:
                continue
            u, v = d.get("uso", {}), d.get("verificacao", {})
            achadas.append(dict(
                modelo=u.get("modelo", "?"), provedor=u.get("provedor", "?"),
                effort=u.get("effort", "?"), modo=d.get("modo", "?"),
                segundos=u.get("segundos", 0), entrada=u.get("entrada", 0),
                cache=u.get("cache_leitura", 0), saida=u.get("saida", 0),
                raciocinio=u.get("raciocinio", 0), usd_estimado=u.get("usd"),
                ancorada=v.get("taxa_ancorada", 0), naoloc=v.get("nao_localizado", 0),
                arquivo=f))
    # de-dup por modelo, ficando com a mais recente
    por: dict[str, dict] = {}
    for e in achadas:
        por[e["modelo"]] = e
    return sorted(por.values(), key=lambda x: x["modelo"])


def main() -> int:
    ap = argparse.ArgumentParser(description="Placar completo de uma licitação")
    ap.add_argument("pasta")
    ap.add_argument("--md", action="store_true", help="imprime em Markdown")
    a = ap.parse_args()

    nome = os.path.basename(a.pasta.rstrip("\\/"))
    execs = execucoes(nome)
    if not execs:
        print("nenhuma execução encontrada para %s" % nome)
        return 2

    # acurácia, onde houver gabarito
    acc: dict[str, tuple] = {}
    gab_path = os.path.join(AMOSTRAS, nome, "_gabarito.json")
    if os.path.isfile(gab_path):
        ac = _acuracia_mod()
        gab = json.load(io.open(gab_path, encoding="utf-8"))
        perguntas = gab["perguntas"]
        criticas = [q for q, r in perguntas.items() if r.get("critica")]
        for e in execs:
            d = json.load(io.open(e["arquivo"], encoding="utf-8"))
            resp = {r["id"]: r.get("resposta", "") for r in d.get("respostas", [])}
            ok = crit = des = des_tot = 0
            for q, ref in perguntas.items():
                r = ac.avaliar(resp.get(q, ""), ref)
                ok += r["correta"]
                des += r["desejaveis"]; des_tot += r["desejaveis_total"]
                if q in criticas:
                    crit += r["correta"]
            acc[e["modelo"]] = (ok, len(perguntas), crit, len(criticas), des, des_tot)

    oa, an = fatura_openai(), fatura_anthropic()
    uso_oa = uso_openai()

    def custo(m: str, e: dict):
        """
        Custo da EXECUÇÃO — que não é o mesmo que a linha da fatura.

        A fatura agrega por modelo e por dia. Se o mesmo modelo rodou mais de
        uma vez na janela — outra licitação, um teste de fumaça, ou a própria
        sessão de trabalho — a linha dele soma tudo, e atribuí-la a UMA execução
        infla o número sem avisar.

        Peguei isso no próprio placar: `claude-opus-5` apareceu com US$ 14,89
        numa extração que custou menos de US$ 1. Era o dia inteiro da conta.

        Critério: só atribui quando os tokens de saída da execução batem com os
        tokens de saída do modelo na janela (5% de folga). Se não batem, houve
        outro uso, e a coluna diz isso em vez de mentir um número.
        """
        v = oa.get(m) or an.get(m)
        if v is None:
            return None, "pendente"
        total_saida = uso_oa.get(m, {}).get("output_tokens")
        if total_saida and e["saida"]:
            razao = e["saida"] / float(total_saida)
            if razao < 0.95:
                return None, "conta do dia"
        elif m in an:
            # A Anthropic não expõe uso por modelo neste script; sem o
            # denominador, não dá para afirmar que a linha é só desta execução.
            return None, "conta do dia"
        return v, None

    linhas = []
    for e in execs:
        m = e["modelo"]
        a_ = acc.get(m)
        usd, nota = custo(m, e)
        linhas.append(dict(
            modelo=m,
            acuracia="%d/%d" % (a_[0], a_[1]) if a_ else "—",
            criticas="%d/%d" % (a_[2], a_[3]) if a_ else "—",
            completude="%d/%d" % (a_[4], a_[5]) if a_ else "—",
            ancoragem="%.0f%%" % (e["ancorada"] * 100),
            naoloc=e["naoloc"], seg=e["segundos"],
            usd=usd, nota=nota, est=e["usd_estimado"]))
    # ordena por acurácia e depois por completude
    def chave(l):
        try:
            a1, a2 = l["acuracia"].split("/"); c1, c2 = l["completude"].split("/")
            return (-int(a1), -int(c1))
        except ValueError:
            return (0, 0)
    linhas.sort(key=chave)

    if a.md:
        print("| modelo | acurácia | críticas | completude | ancoragem | tempo | custo real |")
        print("|---|---|---|---|---|---|---|")
        for l in linhas:
            c = ("US$ %.4f" % l["usd"]) if l["usd"] else l["nota"]
            print("| `%s` | %s | %s | %s | %s | %.0fs | %s |"
                  % (l["modelo"], l["acuracia"], l["criticas"], l["completude"],
                     l["ancoragem"], l["seg"], c))
        return 0

    print("\n" + "=" * 104)
    print("  PLACAR — %s" % nome)
    print("=" * 104)
    print("  %-20s %-9s %-9s %-11s %-10s %-7s %-12s %s"
          % ("modelo", "acurácia", "críticas", "completude", "ancoragem",
             "tempo", "custo real", "estimado"))
    print("  " + "-" * 100)
    for l in linhas:
        c = ("US$ %.4f" % l["usd"]) if l["usd"] else l["nota"]
        e = ("US$ %.4f" % l["est"]) if l["est"] else "—"
        print("  %-20s %-9s %-9s %-11s %-10s %-7.0f %-12s %s"
              % (l["modelo"][:20], l["acuracia"], l["criticas"], l["completude"],
                 l["ancoragem"], l["seg"], c, e))
    print("\n  custo real = fatura do provedor, quando atribuível a ESTA execução.")
    print("    pendente ......  a fatura ainda não publicou (Anthropic leva ~1 dia)")
    print("    conta do dia ..  o modelo rodou mais vezes na janela; a linha da")
    print("                     fatura soma tudo e não é desta execução só")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
