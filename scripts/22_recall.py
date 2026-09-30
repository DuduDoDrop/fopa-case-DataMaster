# -*- coding: utf-8 -*-
"""
Recall da recuperação — o BM25 traz a página que responde?

    python 22_recall.py "ABERTO Concorrencia - Eletronica - Pirapo-RS"
    python 22_recall.py <licitação> --ks 2,4,6,8,12,16

Custo: **R$ 0,00**. Nenhum modelo é chamado. O gabarito diz em qual página está
a resposta de cada pergunta; a recuperação diz quais páginas ela escolheria.
Comparar as duas listas é aritmética.

POR QUE ISTO É A MEDIÇÃO QUE FALTAVA NO RAG
A [[ADR-010]] mostrou que o RAG corta 36% do custo sem perder acurácia. Mas isso
foi medido pelo resultado FINAL, e o resultado final passa pelo modelo — que
pode acertar por outro caminho, ou errar por outro motivo. O elo não medido era o
do meio: **quando o RAG erra, ele erra escondendo a página certa**, e a acurácia
final não distingue isso de um modelo que leu mal.

O `k` é o parâmetro que governa esse elo, e nunca foi varrido. `k=6` foi escolhido
por intuição. Aqui ele deixa de ser intuição.

O QUE ESTE NÚMERO NÃO DIZ
Recall alto não garante resposta certa — a página pode chegar e o modelo ler mal.
Recall baixo, esse sim, garante resposta errada: o que não chega não pode ser
lido. É um teto, não uma promessa.
"""
from __future__ import annotations

import argparse
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
sys.path.insert(0, AQUI)

from fopa import extrator                                    # noqa: E402
from fopa import recuperacao as rec                          # noqa: E402
from fopa.extrator import SEMPRE_INCLUIR                     # noqa: E402
from fopa.questionario import POR_ID                         # noqa: E402

AMOSTRAS = os.path.join(RAIZ, "amostras")
SAIDAS = os.path.join(RAIZ, "saidas")


def alvos_do_gabarito(gab: dict) -> dict[str, set[tuple[str, int]]]:
    """Páginas que contêm a resposta, segundo o gabarito lido à mão."""
    alvos = {}
    for qid, ref in gab["perguntas"].items():
        paginas = {(f["arquivo"], f["pagina"]) for f in ref.get("fonte", [])
                   if f.get("arquivo") and f.get("pagina")}
        if paginas:
            alvos[qid] = paginas
    return alvos


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("licitacao")
    ap.add_argument("--ks", default="2,4,6,8,12,16")
    ap.add_argument("--detalhe", action="store_true")
    a = ap.parse_args()

    pasta = os.path.join(AMOSTRAS, a.licitacao)
    gab_p = os.path.join(pasta, "_gabarito.json")
    if not os.path.isfile(gab_p):
        print("sem gabarito: %s" % os.path.relpath(gab_p, RAIZ))
        print("o recall só pode ser medido onde se sabe qual é a página certa.")
        return 2

    gab = json.load(open(gab_p, encoding="utf-8"))
    alvos = alvos_do_gabarito(gab)
    paginas = extrator.carregar_paginas(pasta)
    indice = rec.IndiceBM25(paginas)
    ks = [int(x) for x in a.ks.split(",") if x.strip()]

    print("=" * 96)
    print("  RECALL DA RECUPERAÇÃO — %s" % a.licitacao)
    print("=" * 96)
    print("  %d páginas · %d perguntas com página conhecida · custo R$ 0,00"
          % (len(paginas), len(alvos)))
    print("  Uma pergunta conta como recuperada quando ao menos uma das páginas")
    print("  do gabarito aparece entre as k escolhidas.\n")

    print("%4s %12s %14s %s" % ("k", "recall", "páginas/perg", "perguntas que ficaram de fora"))
    print("-" * 96)

    detalhado = {}
    for k in ks:
        acertos, fora, total_pag = 0, [], 0
        por_pergunta = {}
        for qid, esperadas in alvos.items():
            escolhidas = rec.paginas_para_pergunta(
                indice, POR_ID[qid], k=k, sempre=SEMPRE_INCLUIR)
            chaves = {(p.arquivo, p.numero) for p in escolhidas}
            total_pag += len(chaves)
            ok = bool(chaves & esperadas)
            por_pergunta[qid] = ok
            if ok:
                acertos += 1
            else:
                fora.append(qid)
        detalhado[k] = por_pergunta
        print("%4d %8d/%-3d %14.1f %s"
              % (k, acertos, len(alvos), total_pag / max(len(alvos), 1),
                 ", ".join(sorted(fora, key=lambda q: int(q[1:]))) or "—"))

    # ---------------------------------------------------- onde o k para de pagar
    print("-" * 96)
    # O k que interessa é o MENOR que atinge o teto, não o primeiro que repete o
    # anterior: repetir um valor baixo no meio da curva não é platô, e reportar
    # isso como "para de melhorar" mandaria parar antes da hora.
    recalls = {k: sum(1 for v in detalhado[k].values() if v) for k in ks}
    teto = max(recalls.values())
    menor = min(k for k in ks if recalls[k] == teto)
    if teto < len(alvos):
        print("  teto de %d/%d em k=%d — %d pergunta(s) nunca são recuperadas, "
              "e aumentar k não resolve" % (teto, len(alvos), menor, len(alvos) - teto))
    elif menor == max(ks):
        print("  o recall só fecha no maior k testado: vale varrer mais alto")
    else:
        print("  k=%d já atinge o teto de %d/%d — acima disso só aumenta o custo"
              % (menor, teto, len(alvos)))
        atual = 6
        if atual in recalls and recalls[atual] == teto and menor < atual:
            print("  o k=%d em uso entrega o mesmo recall com %d páginas a mais "
                  "por pergunta" % (atual, atual - menor))

    if a.detalhe:
        print("\n  por pergunta (k -> recuperou?):")
        for qid in sorted(alvos, key=lambda q: int(q[1:])):
            marcas = " ".join("%d:%s" % (k, "sim" if detalhado[k][qid] else "NÃO")
                              for k in ks)
            crit = " [CRÍTICA]" if gab["perguntas"][qid].get("critica") else ""
            print("    %-4s%-11s %s" % (qid, crit, marcas))

    dest = os.path.join(SAIDAS, "_recall_%s.json" % a.licitacao)
    with open(dest, "w", encoding="utf-8") as f:
        json.dump({"licitacao": a.licitacao,
                   "recall": {str(k): detalhado[k] for k in ks}}, f,
                  ensure_ascii=False, indent=1)
    print("\n  salvo: %s" % os.path.relpath(dest, RAIZ))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
