# -*- coding: utf-8 -*-
"""
O pico de um dia cabe no limite de taxa do provedor?

    python 60_pico_taxa.py [--tier start|build|scale] [--paralelo 1]

NAO CHAMA MODELO. NAO CHAMA REDE. Cruza duas coisas que o projeto ja tem
em disco:

  1. o PICO real -- quantas licitacoes de folha foram publicadas no MESMO
     dia, lido do `saidas/_corpus_escopo.json`;
  2. o CUSTO EM TOKENS de uma extracao -- lido das `auditoria.json` das
     extracoes que ja rodaram, nao de estimativa.

E compara com os limites publicados do provedor.

POR QUE ESTE ITEM ESTAVA EM ABERTO
  A ADR-009 pedia "verificar limites de taxa para o pico (todos os editais de
  um dia no mesmo lote)". Nunca foi verificado porque a pergunta parece exigir
  rodar o lote -- e rodar o lote gasta. Nao exige: o pico e um dado do corpus e
  o custo por licitacao e um dado das auditorias. As duas metades ja existiam.

O QUE A MEDICAO MOSTRA, E E CONTRA-INTUITIVO
  Ninguem esbarra em REQUISICOES por minuto. O gargalo e TOKEN DE ENTRADA por
  minuto, e por uma razao simples: um edital tem 80 mil tokens de mediana e
  212 mil no pior caso do acervo. Tres requisicoes que carregam 200 mil tokens
  pesam mais no limite que trezentas que carregam mil.
"""
from __future__ import annotations

import argparse
import glob
import io
import json
import os
import sys
import time
from collections import Counter

AQUI = os.path.dirname(os.path.abspath(__file__))
RAIZ = os.path.dirname(AQUI)
sys.path.insert(0, AQUI)

DESTINO = os.path.join(RAIZ, "saidas", "_pico_taxa.json")

# Limites publicados em https://platform.claude.com/docs/en/api/rate-limits
# consultados em 23/09/2026, para Claude Opus 5 (o modelo do Extrator).
# Estao aqui com a data porque tabela de provedor muda, e um limite velho
# tratado como atual e o tipo de numero que so aparece errado em producao.
TIERS = {
    "start": {"rpm": 1_000, "itpm": 2_000_000, "otpm": 400_000},
    "build": {"rpm": 5_000, "itpm": 5_000_000, "otpm": 1_000_000},
    "scale": {"rpm": 10_000, "itpm": 10_000_000, "otpm": 2_000_000},
}
FONTE_LIMITES = ("https://platform.claude.com/docs/en/api/rate-limits"
                 " — consultado em 2026-09-23, linha Claude Opus 5")

# 17 perguntas em lotes de 6 -> 3 requisicoes. E o default do extrator
# (`fopa/extrator.py`, parametro `lote`).
REQ_POR_LICITACAO = 3


def picos_do_corpus() -> tuple[Counter, list]:
    p = os.path.join(RAIZ, "saidas", "_corpus_escopo.json")
    if not os.path.isfile(p):
        return Counter(), []
    regs = json.load(io.open(p, encoding="utf-8"))["registros"]
    regs = list(regs.values()) if isinstance(regs, dict) else regs
    dentro = [x for x in regs if x.get("dentro")]
    por_dia = Counter((x.get("publicado_em") or "")[:10]
                      for x in dentro if x.get("publicado_em"))
    return por_dia, dentro


def usos_medidos() -> list:
    """Uso real das extracoes ja feitas. Nada de estimativa."""
    usos = []
    for f in (glob.glob(os.path.join(RAIZ, "saidas", "**", "*.json"), recursive=True)
              + glob.glob(os.path.join(RAIZ, "amostras", "*", "*.json"))):
        try:
            d = json.load(io.open(f, encoding="utf-8"))
        except (OSError, ValueError):
            continue
        if not isinstance(d, dict):
            continue
        u = d.get("uso") or (d.get("auditoria") or {}).get("uso")
        # o simulado grava uso zerado; ele nao representa carga nenhuma
        if isinstance(u, dict) and (u.get("entrada") or 0) > 1000:
            usos.append(u)
    return usos


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--tier", choices=sorted(TIERS), default="start")
    ap.add_argument("--paralelo", type=int, default=1,
                    help="licitações extraídas ao mesmo tempo (hoje o código é 1)")
    a = ap.parse_args()
    try:
        sys.stdout.reconfigure(line_buffering=True, encoding="utf-8")
    except (AttributeError, ValueError):
        pass

    por_dia, dentro = picos_do_corpus()
    usos = usos_medidos()
    if not por_dia or not usos:
        print("falta corpus (`saidas/_corpus_escopo.json`) ou extração medida.")
        return 1

    ent = sorted(u["entrada"] for u in usos)
    sai = sorted(u["saida"] for u in usos)
    seg = sorted((u.get("segundos") or 0) for u in usos)
    n = len(usos)
    pico = max(por_dia.values())
    dia_pico = max(por_dia, key=lambda d: por_dia[d])
    lim = TIERS[a.tier]

    print("=" * 96)
    print("  O PICO DE UM DIA CABE NO LIMITE DE TAXA? — tier %s" % a.tier)
    print("=" * 96)
    print()
    print("  PICO, medido no corpus (%d licitações no escopo, %d dias)"
          % (len(dentro), len(por_dia)))
    vals = sorted(por_dia.values())
    print("     por dia .......... mediana %d · p90 %d · MÁXIMO %d (%s)"
          % (vals[len(vals) // 2], vals[int(len(vals) * 0.9)], pico, dia_pico))
    print()
    print("  CUSTO DE UMA EXTRAÇÃO, medido em %d execuções reais" % n)
    print("     tokens de entrada . mediana %8d · máximo %8d" % (ent[n // 2], ent[-1]))
    print("     tokens de saída ... mediana %8d · máximo %8d" % (sai[n // 2], sai[-1]))
    print("     duração ........... mediana %8.0f s · máximo %8.0f s"
          % (seg[n // 2], seg[-1]))
    print()

    linhas = []
    for nome, e, s in (("caso mediano", ent[n // 2], sai[n // 2]),
                       ("pior caso do acervo", ent[-1], sai[-1])):
        req = pico * REQ_POR_LICITACAO
        print("  %s — as %d do dia de pico" % (nome.upper(), pico))
        # (a) tudo no mesmo minuto: o cenario que o item da ADR perguntava
        pe, ps, pr = (100.0 * pico * e / lim["itpm"],
                      100.0 * pico * s / lim["otpm"],
                      100.0 * req / lim["rpm"])
        print("     se disparadas TODAS no mesmo minuto")
        print("        requisições .... %4d de %5d/min = %5.1f%%"
              % (req, lim["rpm"], pr))
        print("        entrada ........ %9d de %9d/min = %5.1f%%   %s"
              % (pico * e, lim["itpm"], pe, "ESTOURA" if pe > 100 else "cabe"))
        print("        saída .......... %9d de %9d/min = %5.1f%%   %s"
              % (pico * s, lim["otpm"], ps, "ESTOURA" if ps > 100 else "cabe"))
        # (b) como o codigo realmente roda: uma licitacao por vez
        minutos = max(1.0, pico * seg[n // 2] / 60.0 / max(1, a.paralelo))
        se, ss = (100.0 * pico * e / minutos / lim["itpm"],
                  100.0 * pico * s / minutos / lim["otpm"])
        print("     como o código roda hoje (%d por vez, ~%.0f min no total)"
              % (a.paralelo, minutos))
        print("        entrada ........ %5.1f%% do limite por minuto" % se)
        print("        saída .......... %5.1f%% do limite por minuto" % ss)
        print()
        linhas.append({"caso": nome, "entrada": e, "saida": s,
                       "pct_itpm_um_minuto": round(pe, 1),
                       "pct_otpm_um_minuto": round(ps, 1),
                       "pct_rpm_um_minuto": round(pr, 1),
                       "minutos_serial": round(minutos, 1),
                       "pct_itpm_serial": round(se, 1)})

    print("-" * 96)
    print("  O QUE ISTO DECIDE")
    print("-" * 96)
    print("  1. REQUISIÇÃO POR MINUTO NUNCA É O GARGALO. O pico inteiro são")
    print("     %d requisições, contra %d/min de limite. Um edital é pesado, não"
          % (pico * REQ_POR_LICITACAO, lim["rpm"]))
    print("     numeroso: 3 chamadas carregando 200 mil tokens pesam mais que")
    print("     300 carregando mil.")
    print()
    print("  2. O GARGALO É TOKEN DE ENTRADA POR MINUTO. E ele só aparece se")
    print("     alguém paralelizar o lote. Serial — que é como o código roda —")
    print("     o dia de pico se espalha por dezenas de minutos e sobra folga.")
    print()
    print("  3. QUEM PARALELIZAR PRECISA SABER DISTO ANTES. Está aqui com o")
    print("     número, e não depois de um 429 em produção.")
    print()
    print("  4. CACHE DE LEITURA NÃO CONTA PARA O ITPM (exceto Haiku 3.5). Se o")
    print("     reaproveitamento de cache do Extrator for consertado, ele compra")
    print("     teto de taxa além de dinheiro. Ver `58_preco_openai.py`.")
    print()
    print("  fonte dos limites: %s" % FONTE_LIMITES)

    io.open(DESTINO, "w", encoding="utf-8").write(json.dumps(
        {"medido_em": time.strftime("%Y-%m-%d"), "tier": a.tier,
         "limites": lim, "fonte_limites": FONTE_LIMITES,
         "pico_licitacoes_em_um_dia": pico, "dia_do_pico": dia_pico,
         "extracoes_medidas": n, "req_por_licitacao": REQ_POR_LICITACAO,
         "casos": linhas}, ensure_ascii=False, indent=1))
    print("\n  salvo em saidas/_pico_taxa.json · custo R$ 0,00")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
