# -*- coding: utf-8 -*-
"""
Roda o pipeline em TODAS as licitações baixadas e consolida o resultado.

É o teste de robustez: cada pasta tem uma forma diferente — dispensa sem arquivo
do tipo "Edital", credenciamento com arquivo único, conjuntos digitalizados que
exigem OCR pesado. Rodar só numa licitação prova pouco.

    python 12_lote.py --simulado          ensaio, sem gastar token
    python 12_lote.py                     execução real
    python 12_lote.py --modelo claude-sonnet-5
    python 12_lote.py --so ABERTO         só as pastas que começam com isso
"""
from __future__ import annotations

import argparse
import json
import os
import sys
import time
import traceback

for _f in (sys.stdout, sys.stderr):
    try:
        _f.reconfigure(encoding="utf-8", errors="replace")
    except (AttributeError, ValueError):
        pass

AQUI = os.path.dirname(os.path.abspath(__file__))
RAIZ = os.path.dirname(AQUI)
sys.path.insert(0, AQUI)

from fopa import extrator, metadados, modelos, pagina, saida, verificador  # noqa: E402

AMOSTRAS = os.path.join(RAIZ, "amostras")
SAIDAS = os.path.join(RAIZ, "saidas")


def pastas(filtro: str | None) -> list[str]:
    fora = {"_fixture", "_ocr_benchmark"}
    itens = []
    for n in sorted(os.listdir(AMOSTRAS)):
        p = os.path.join(AMOSTRAS, n)
        if not os.path.isdir(p) or n in fora or n.startswith("_"):
            continue
        if filtro and not n.startswith(filtro):
            continue
        if any(f.lower().endswith(".pdf") for f in os.listdir(p)):
            itens.append(p)
    return itens


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--simulado", action="store_true")
    ap.add_argument("--provedor", choices=sorted(modelos.PROVEDORES),
                    default="claude", help="claude (padrão), openai (plano B) ou simulado")
    ap.add_argument("--modelo", default=modelos.MODELO_EXTRATOR)
    ap.add_argument("--modo", choices=["contexto-completo", "rag"], default=None)
    ap.add_argument("--so", default=None, help="prefixo para filtrar pastas")
    ap.add_argument("--lote", type=int, default=6)
    a = ap.parse_args()

    alvos = pastas(a.so)
    print("=" * 96)
    print("  LOTE — %d licitações · modelo %s%s"
          % (len(alvos), "simulado" if a.simulado else a.modelo,
             "" if not a.modo else " · modo forçado %s" % a.modo))
    print("=" * 96)

    try:
        provedor = modelos.obter_provedor(simulado=a.simulado,
                                          provedor=a.provedor)
    except modelos.ErroModelo as e:
        print("\n  %s" % e)
        return 3

    linhas, falhas = [], []
    t_inicio = time.time()

    for i, pasta in enumerate(alvos, start=1):
        nome = os.path.basename(pasta)
        print("\n[%2d/%d] %s" % (i, len(alvos), nome))
        t0 = time.time()
        try:
            ext = extrator.extrair(pasta, provedor, modelo=a.modelo,
                                   modo=a.modo, lote=a.lote)
            rel = verificador.verificar(ext)
            destino = os.path.join(SAIDAS, nome)
            saida.escrever_json(ext, rel, os.path.join(destino, "auditoria.json"))
            saida.escrever_nota(ext, rel, os.path.join(destino, "%s.md" % nome))
            try:
                saida.escrever_xlsx(ext, rel, os.path.join(destino, "%s.xlsx" % nome))
            except RuntimeError:
                pass
            metadados.atualizar(pasta, ext, rel)
            pagina.escrever(ext, rel, os.path.join(pasta, "RELATORIO.html"))

            linhas.append(dict(
                licitacao=nome, arquivos=len(ext.arquivos), paginas=len(ext.paginas),
                modo=ext.modo, modelo=ext.uso.modelo, chamadas=ext.uso.chamadas,
                entrada=ext.uso.entrada, saida_tok=ext.uso.saida,
                ancoradas=rel.ancoradas, respondidas=rel.respondidas,
                taxa=round(rel.taxa_ancorada, 4),
                aprovadas=rel.aprovadas, revisar=rel.revisar,
                reprovadas=rel.reprovadas, nao_loc=rel.nao_localizado,
                conflitos=sum(1 for r in ext.respostas if r.conflito),
                brl=round(ext.uso.brl, 3), seg=round(time.time() - t0, 1)))
            print("        %d arq · %3d pág · %-16s | %s | R$ %.2f · %.0fs"
                  % (len(ext.arquivos), len(ext.paginas), ext.modo, rel,
                     ext.uso.brl, time.time() - t0))
        except Exception as e:                                  # noqa: BLE001
            falhas.append((nome, repr(e)))
            print("        FALHOU: %s" % e)
            traceback.print_exc(limit=2)

    # ---------------------------------------------------------- consolidado
    print("\n" + "=" * 96)
    print("  CONSOLIDADO")
    print("=" * 96)
    print("%-46s %4s %5s %-16s %9s %7s %6s" %
          ("licitação", "arq", "pág", "modo", "ancoragem", "confl.", "R$"))
    print("-" * 96)
    for r in linhas:
        print("%-46s %4d %5d %-16s %4d/%-4d %7d %6.2f"
              % (r["licitacao"][:46], r["arquivos"], r["paginas"], r["modo"],
                 r["ancoradas"], r["respondidas"], r["conflitos"], r["brl"]))

    if linhas:
        tot_anc = sum(r["ancoradas"] for r in linhas)
        tot_resp = sum(r["respondidas"] for r in linhas)
        print("-" * 96)
        print("%-46s %4d %5d %-16s %4d/%-4d %7d %6.2f"
              % ("TOTAL (%d licitações)" % len(linhas),
                 sum(r["arquivos"] for r in linhas), sum(r["paginas"] for r in linhas),
                 "", tot_anc, tot_resp, sum(r["conflitos"] for r in linhas),
                 sum(r["brl"] for r in linhas)))
        print("\n  ancoragem global .. %d/%d (%.1f%%)"
              % (tot_anc, tot_resp, 100.0 * tot_anc / max(tot_resp, 1)))
        print("  reprovadas ........ %d" % sum(r["reprovadas"] for r in linhas))
        print("  não localizado .... %d" % sum(r["nao_loc"] for r in linhas))
        print("  custo total ....... R$ %.2f" % sum(r["brl"] for r in linhas))
        print("  tempo total ....... %.1f min" % ((time.time() - t_inicio) / 60))

    if falhas:
        print("\n  FALHAS (%d):" % len(falhas))
        for n, e in falhas:
            print("    %-46s %s" % (n[:46], e[:70]))

    destino = os.path.join(SAIDAS, "_lote_%s.json"
                           % ("simulado" if a.simulado else a.modelo))
    os.makedirs(SAIDAS, exist_ok=True)
    with open(destino, "w", encoding="utf-8") as f:
        json.dump({"modelo": "simulado" if a.simulado else a.modelo,
                   "linhas": linhas, "falhas": falhas}, f,
                  ensure_ascii=False, indent=1)
    print("\n  salvo: %s" % os.path.relpath(destino, RAIZ))
    return 1 if falhas else 0


if __name__ == "__main__":
    raise SystemExit(main())
