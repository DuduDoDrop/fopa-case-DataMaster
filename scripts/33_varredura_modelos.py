# -*- coding: utf-8 -*-
"""
Varredura: a MESMA licitação em vários modelos, com teto de gasto.

    python 33_varredura_modelos.py "<pasta>" --modelos gpt-6-astra gpt-6-sol
    python 33_varredura_modelos.py "<pasta>" --teto 3.00
    python 33_varredura_modelos.py "<pasta>" --seco      só orça, não roda

POR QUE TETO DE GASTO, E NÃO CONFIANÇA
  Porque o custo de um modelo desconhecido é desconhecido — é o ponto de medi-lo.
  `gpt-6-astra` custa 2,5× o `gpt-5.6-sol`; um `-pro` pode custar muito mais. Uma
  varredura sem teto é um jeito elegante de descobrir o preço depois de pagá-lo.

  O teto é conferido **na fatura**, entre um modelo e outro, não numa estimativa:
  a API de custos da OpenAI responde em segundos e separa por `line_item`.

O QUE ELA MEDE
  Ancoragem e custo por modelo, no mesmo edital e na mesma configuração. Acurácia
  sai depois, pelo `15_acuracia.py --extra`, onde houver gabarito — e só ele diz
  quem ACERTOU. Ancoragem empata entre modelos bons; é a profundidade que separa.
"""
from __future__ import annotations

import argparse
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

from fopa import extrator, modelos, saida, segredos, verificador   # noqa: E402

AMOSTRAS = os.path.join(RAIZ, "amostras")
SAIDAS = os.path.join(RAIZ, "saidas")


def barra(t: str) -> None:
    print("\n" + "=" * 100 + "\n  %s\n" % t + "=" * 100)


def custo_por_modelo(horas: int = 24) -> dict[str, float]:
    """Custo cobrado, por modelo, direto da fatura."""
    chave = segredos.obter("OPENAI_ADMIN_KEY")
    if not chave:
        return {}
    ini = int(time.time()) - 3600 * horas
    url = ("https://api.openai.com/v1/organization/costs?start_time=%d"
           "&limit=31&group_by[]=line_item" % ini)
    try:
        req = urllib.request.Request(url, headers={"Authorization": "Bearer %s" % chave})
        with urllib.request.urlopen(req, timeout=40) as r:
            d = json.loads(r.read().decode("utf-8"))
    except Exception:                                              # noqa: BLE001
        return {}
    por: dict[str, float] = defaultdict(float)
    for b in d.get("data", []):
        for x in b.get("results", []):
            li = x.get("line_item") or ""
            m = li.split(",")[0].strip()          # "gpt-6-astra, output" -> modelo
            por[m] += (x.get("amount") or {}).get("value") or 0.0
    return dict(por)


def total(d: dict[str, float]) -> float:
    return sum(d.values())


def main() -> int:
    ap = argparse.ArgumentParser(description="Mesma licitação em vários modelos")
    ap.add_argument("pasta")
    ap.add_argument("--modelos", nargs="+", required=True)
    ap.add_argument("--teto", type=float, default=3.0,
                    help="gasto máximo em USD (conferido na fatura)")
    ap.add_argument("--effort", choices=["low", "medium", "high"], default="high")
    ap.add_argument("--lote", type=int, default=6)
    ap.add_argument("--k", type=int, default=6)
    ap.add_argument("--seco", action="store_true")
    a = ap.parse_args()

    pasta = a.pasta if os.path.isdir(a.pasta) else os.path.join(AMOSTRAS, a.pasta)
    if not os.path.isdir(pasta):
        print("pasta não encontrada: %s" % pasta)
        return 2
    nome = os.path.basename(pasta.rstrip("\\/"))
    base = os.path.join(SAIDAS, "_varredura_%s" % nome)

    barra("VARREDURA — %s" % nome)
    print("  modelos .... %s" % ", ".join(a.modelos))
    print("  effort ..... %s   lote %d   k %d" % (a.effort, a.lote, a.k))
    print("  teto ....... US$ %.2f (conferido na fatura entre um modelo e outro)"
          % a.teto)

    antes = custo_por_modelo()
    partida = total(antes)
    print("  gasto atual  US$ %.4f" % partida)

    if a.seco:
        print("\n  (--seco: nada executado)")
        return 0

    resultados = []
    for i, m in enumerate(a.modelos, 1):
        gasto = total(custo_por_modelo()) - partida
        if gasto >= a.teto:
            print("\n  TETO ATINGIDO (US$ %.4f de US$ %.2f). Parando antes de %s."
                  % (gasto, a.teto, m))
            break

        print("\n  [%d/%d] %s   (gasto até aqui US$ %.4f)"
              % (i, len(a.modelos), m, gasto), flush=True)
        try:
            prov = modelos.obter_provedor(provedor="openai")
            t0 = time.time()
            ext = extrator.extrair(pasta, prov, modelo=m, lote=a.lote,
                                   k_rag=a.k, effort=a.effort)
            rel = verificador.verificar(ext)
            destino = os.path.join(base, m)
            os.makedirs(destino, exist_ok=True)
            saida.escrever_json(ext, rel, os.path.join(destino, "auditoria.json"))
            resultados.append(dict(modelo=m, uso=ext.uso, rel=rel, modo=ext.modo,
                                   seg=time.time() - t0))
            print("     %s" % ext.uso)
            print("     %s" % rel)
        except Exception as e:                                     # noqa: BLE001
            print("     FALHOU: %s" % str(e)[:200])
            resultados.append(dict(modelo=m, erro=str(e)[:200]))

    # a contabilidade não é instantânea; dar uma folga antes do fechamento
    print("\n  aguardando a fatura fechar...", flush=True)
    time.sleep(25)
    depois = custo_por_modelo()

    barra("PLACAR — %s" % nome)
    print("  %-16s %-9s %-7s %-7s %-9s %-10s %s"
          % ("modelo", "ancorag.", "n/loc", "revisar", "tokens", "US$ fatura", "tempo"))
    print("  " + "-" * 96)
    for r in resultados:
        if r.get("erro"):
            print("  %-16s FALHOU: %s" % (r["modelo"][:16], r["erro"][:60]))
            continue
        u, rel = r["uso"], r["rel"]
        usd = depois.get(r["modelo"], 0) - antes.get(r["modelo"], 0)
        print("  %-16s %6.0f%%   %-7d %-7d %-9s %-10s %.0fs"
              % (r["modelo"][:16], rel.taxa_ancorada * 100, rel.nao_localizado,
                 rel.revisar, f"{u.entrada + u.cache_leitura + u.saida:,}".replace(",", "."),
                 "%.4f" % usd if usd > 0 else "—", r["seg"]))

    gasto = total(depois) - partida
    print("\n  gasto da varredura: US$ %.4f  (R$ %.2f)" % (gasto, gasto * modelos.USD_BRL))
    print("  saídas em %s" % os.path.relpath(base, RAIZ))

    gab = os.path.join(pasta, "_gabarito.json")
    if os.path.isfile(gab):
        extras = " ".join('--extra "%s"' % os.path.join(base, r["modelo"], "auditoria.json")
                          for r in resultados if not r.get("erro"))
        print("\n  Há gabarito — para saber quem ACERTOU:")
        print('      python 15_acuracia.py "%s" %s' % (nome, extras))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
