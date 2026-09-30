# -*- coding: utf-8 -*-
"""
Consolida TODAS as comparações do harness num quadro único.

    python 17_benchmark.py
    python 17_benchmark.py --json        despeja o consolidado em saidas/_benchmark.json

Cada `_harness_*.json` compara configurações **dentro** de uma licitação. Este
script cruza o outro eixo: a mesma configuração **através** das licitações, que é
o número que vai para a apresentação.

A média simples entre licitações seria enganosa — um edital de 6 páginas e um de
115 pesam igual numa média e não pesam igual na fatura. Por isso o custo aparece
somado e por edital, e a ancoragem aparece como razão agregada (total ancorado
sobre total respondido), não como média de porcentagens.
"""
from __future__ import annotations

import argparse
import glob
import json
import os
import sys

for _f in (sys.stdout, sys.stderr):
    try:
        _f.reconfigure(encoding="utf-8", errors="replace")
    except (AttributeError, ValueError):
        pass

AQUI = os.path.dirname(os.path.abspath(__file__))
RAIZ = os.path.dirname(AQUI)
SAIDAS = os.path.join(RAIZ, "saidas")

# Varreduras de effort e de modo comparam outra coisa; entram só as de modelo.
IGNORAR = ("_efforts", "_modos")


def familia(rotulo: str) -> str:
    return rotulo.split(" · ")[0]


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--json", action="store_true")
    a = ap.parse_args()

    arquivos = [f for f in sorted(glob.glob(os.path.join(SAIDAS, "_harness_*.json")))
                if not any(t in os.path.basename(f) for t in IGNORAR)]
    if not arquivos:
        print("nenhuma comparação encontrada.")
        return 2

    por_modelo: dict[str, dict] = {}
    linhas = []

    for f in arquivos:
        d = json.load(open(f, encoding="utf-8"))
        lic = d.get("licitacao", "")
        for e in d.get("execucoes", []):
            m = familia(e["rotulo"])
            acc = por_modelo.setdefault(m, dict(
                lic=0, anc=0, resp=0, confl=0, naoloc=0, revisar=0,
                reprov=0, brl=0.0, seg=0.0, ent=0, sai=0))
            acc["lic"] += 1
            acc["anc"] += e.get("ancoradas", 0)
            acc["resp"] += e.get("respondidas", 0)
            acc["confl"] += e.get("conflitos", 0)
            acc["naoloc"] += e.get("nao_loc", 0)
            acc["revisar"] += e.get("revisar", 0)
            acc["reprov"] += e.get("reprovadas", 0)
            acc["brl"] += e.get("brl", 0.0)
            acc["seg"] += e.get("seg", 0.0)
            acc["ent"] += e.get("entrada", 0)
            acc["sai"] += e.get("saida", 0)
            linhas.append(dict(licitacao=lic, modelo=m, modo=e.get("modo"),
                               ancoradas=e.get("ancoradas"),
                               respondidas=e.get("respondidas"),
                               conflitos=e.get("conflitos"),
                               brl=e.get("brl"), seg=e.get("seg")))

    print("=" * 104)
    print("  BENCHMARK CONSOLIDADO — %d licitações comparadas" % len(arquivos))
    print("=" * 104)
    print("%-14s %5s %11s %8s %8s %8s %9s %9s %8s"
          % ("modelo", "lics", "ancoragem", "confl", "não-loc", "revisar",
             "R$ total", "R$/edital", "s/edital"))
    print("-" * 104)

    ordem = sorted(por_modelo, key=lambda m: -por_modelo[m]["brl"])
    base = None
    for m in ordem:
        v = por_modelo[m]
        taxa = 100.0 * v["anc"] / max(v["resp"], 1)
        if base is None:
            base = v["brl"] / max(v["lic"], 1)
        print("%-14s %5d %5d/%-5d %8d %8d %8d %9.2f %9.2f %8.0f"
              % (m, v["lic"], v["anc"], v["resp"], v["confl"], v["naoloc"],
                 v["revisar"], v["brl"], v["brl"] / max(v["lic"], 1),
                 v["seg"] / max(v["lic"], 1)))

    print("-" * 104)
    for m in ordem:
        v = por_modelo[m]
        por_edital = v["brl"] / max(v["lic"], 1)
        taxa = 100.0 * v["anc"] / max(v["resp"], 1)
        delta = "" if base in (None, 0) else "  custo %+.0f%%" % (
            100.0 * (por_edital - base) / base)
        print("  %-14s ancoragem %5.1f%% · %d conflito(s) em %d edital(is)%s"
              % (m, taxa, v["confl"], v["lic"], delta))

    # ------------------------------------------------- recorte comparável
    # Médias sobre conjuntos diferentes não se comparam. O Haiku rodou em 2
    # licitações e os outros em 7: sem este recorte, a taxa de "não localizado"
    # dele parece MELHOR que a do Opus, quando na verdade ele só viu os dois
    # editais em que todos foram bem.
    por_lic: dict[str, set] = {}
    for ln in linhas:
        por_lic.setdefault(ln["licitacao"], set()).add(ln["modelo"])
    comuns = {lic for lic, ms in por_lic.items() if ms >= set(por_modelo)}

    if comuns and len(comuns) < len(por_lic):
        print()
        print("=" * 104)
        print("  RECORTE COMPARÁVEL — as %d licitação(ões) em que TODOS os %d modelos rodaram"
              % (len(comuns), len(por_modelo)))
        print("=" * 104)
        print("%-14s %11s %8s %9s %9s" % ("modelo", "ancoragem", "confl", "R$ total", "R$/edital"))
        print("-" * 104)
        base_c = None
        for m in ordem:
            sel = [l for l in linhas if l["modelo"] == m and l["licitacao"] in comuns]
            anc = sum(l["ancoradas"] or 0 for l in sel)
            resp = sum(l["respondidas"] or 0 for l in sel)
            confl = sum(l["conflitos"] or 0 for l in sel)
            brl = sum(l["brl"] or 0 for l in sel)
            pe = brl / max(len(sel), 1)
            if base_c is None:
                base_c = pe
            print("%-14s %5d/%-5d %8d %9.2f %9.2f%s"
                  % (m, anc, resp, confl, brl, pe,
                     "" if not base_c else "   %+.0f%%" % (100.0 * (pe - base_c) / base_c)))

    # O que a ancoragem não mostra: quem desiste de responder.
    print()
    print("  Taxa de \"não localizado\" — quantas das 17 o modelo deixou em branco:")
    for m in ordem:
        v = por_modelo[m]
        print("    %-14s %4.1f por edital  (em %d licitação(ões))"
              % (m, v["naoloc"] / max(v["lic"], 1), v["lic"]))

    if a.json:
        dest = os.path.join(SAIDAS, "_benchmark.json")
        with open(dest, "w", encoding="utf-8") as f:
            json.dump({"por_modelo": por_modelo, "linhas": linhas}, f,
                      ensure_ascii=False, indent=1)
        print("\n  salvo: %s" % os.path.relpath(dest, RAIZ))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
