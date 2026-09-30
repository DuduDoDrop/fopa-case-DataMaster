# -*- coding: utf-8 -*-
"""
Gera o painel — `amostras/index.html`.

    python 16_painel.py
    python 16_painel.py --abrir

A porta de entrada para quem não vai abrir um JSON. Lê o que já existe no disco
(`_inventario.json` de cada licitação e `auditoria.json` de cada extração) e não
chama modelo nenhum: **custo R$ 0,00**, e pode rodar ao fim de todo lote.

Fica dentro de `amostras/` de propósito. É o que faz os links relativos abrirem
o relatório de cada licitação e os PDFs originais sem precisar de servidor —
duplo clique resolve, que é como a área de negócio vai usar.
"""
from __future__ import annotations

import argparse
import os
import sys
import webbrowser

for _f in (sys.stdout, sys.stderr):
    try:
        _f.reconfigure(encoding="utf-8", errors="replace")
    except (AttributeError, ValueError):
        pass

AQUI = os.path.dirname(os.path.abspath(__file__))
RAIZ = os.path.dirname(AQUI)
sys.path.insert(0, AQUI)

from fopa import painel                                  # noqa: E402

AMOSTRAS = os.path.join(RAIZ, "amostras")
SAIDAS = os.path.join(RAIZ, "saidas")


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--abrir", action="store_true", help="abre no navegador ao terminar")
    ap.add_argument("--saida", default=os.path.join(AMOSTRAS, "index.html"))
    a = ap.parse_args()

    if not os.path.isdir(AMOSTRAS):
        print("pasta de amostras não encontrada: %s" % AMOSTRAS)
        return 2

    destino = painel.escrever(AMOSTRAS, SAIDAS, a.saida)
    itens = painel.coletar(AMOSTRAS, SAIDAS, __import__("datetime").date.today())
    extraidas = sum(1 for i in itens if i["aud"])
    urgentes = sum(1 for i in itens if i["dias"] is not None and 0 <= i["dias"] <= 7)

    print("painel gerado: %s" % os.path.relpath(destino, RAIZ))
    print("  %d licitações · %d extraídas · %d fecham em ≤7 dias"
          % (len(itens), extraidas, urgentes))
    print("  custo em API: R$ 0,00")

    if a.abrir:
        webbrowser.open("file:///" + destino.replace("\\", "/"))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
