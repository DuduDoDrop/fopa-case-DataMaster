# -*- coding: utf-8 -*-
"""
O `consulta/v1` trunca mesmo em intervalo largo, ou era a pagina curta?

    python 61_truncamento_janela.py [--ini 20260824] [--fim 20260828] [--mod 4]

NAO CHAMA MODELO. So o `consulta/v1`.

A PERGUNTA, E POR QUE ELA PRECISA SER REFEITA
  Em 23/09/2026 o projeto registrou como achado central que o `consulta/v1`
  "trunca em silencio quando o intervalo e largo": 24 a 28/08, modalidade 4,
  deu 1.250 registros dia a dia e 170 a semana de uma vez -- 86% sumindo.
  Ficou escrito que o corte era do lado do SERVIDOR, "onde nenhum cuidado
  do cliente alcanca".

  Horas depois apareceu outro defeito, e este e do lado do CLIENTE: o
  `consulta/v1` devolve PAGINA CURTA NO MEIO do conjunto, e a paginacao do
  projeto parava nela. Num dia medido isso entregava 70 de 3.008 registros.

  As duas medicoes de 86% usaram a paginacao quebrada. Entao a conclusao
  "o servidor trunca" pode ter sido um diagnostico errado do defeito local:
  na consulta da semana, o registro procurado cai depois de uma pagina curta;
  na consulta do dia, cai antes.

  Nao da para saber sem refazer. Este script refaz.

O TESTE
  A mesma janela, dos dois jeitos, AGORA com paginacao completa
  (`pncp.varrer_publicacao`, que le ate o `totalPaginas` declarado):

      A) um dia por vez, somando os conjuntos
      B) a janela inteira de uma vez

  Se A e B derem o MESMO conjunto, o truncamento por janela larga nunca
  existiu -- era a pagina curta o tempo todo, e a nota precisa ser corrigida.
  Se B continuar menor, o achado original se confirma, agora sem a
  contaminacao.

  O script tambem confere o caso individual que tornou o achado "inescapavel":
  Sao Lourenco do Sul/RS, publicada em 26/08. Um conjunto pode ter o mesmo
  TAMANHO e conteudo diferente; e o caso nomeado que fecha a duvida.
"""
from __future__ import annotations

import argparse
import datetime as dt
import io
import json
import os
import sys
import time

AQUI = os.path.dirname(os.path.abspath(__file__))
RAIZ = os.path.dirname(AQUI)
sys.path.insert(0, AQUI)

from fopa import pncp                                             # noqa: E402

DESTINO = os.path.join(RAIZ, "saidas", "_truncamento_janela.json")

# o caso nomeado na nota: aparece na consulta do dia 26 e nao na do mes
CASO = "87893111000152-1-000381/2026"
CASO_NOME = "São Lourenço do Sul/RS, Concorrência 9/2026, publicada em 26/08"


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--ini", default="20260824")
    ap.add_argument("--fim", default="20260828")
    ap.add_argument("--mod", type=int, default=4,
                    help="4 = Concorrência Eletrônica, a da medição original")
    ap.add_argument("--pausa", type=float, default=pncp.PAUSA_VARREDURA)
    a = ap.parse_args()
    try:
        sys.stdout.reconfigure(line_buffering=True, encoding="utf-8")
    except (AttributeError, ValueError):
        pass

    d0 = dt.date(int(a.ini[:4]), int(a.ini[4:6]), int(a.ini[6:]))
    d1 = dt.date(int(a.fim[:4]), int(a.fim[4:6]), int(a.fim[6:]))
    dias = [d0 + dt.timedelta(days=k) for k in range((d1 - d0).days + 1)]

    print("=" * 96)
    print("  TRUNCAMENTO POR JANELA LARGA — o achado ainda vale?")
    print("  janela %s a %s · modalidade %d · paginação COMPLETA"
          % (a.ini, a.fim, a.mod))
    print("=" * 96)
    print()

    # ------------------------------------------------------------ A: dia a dia
    print("  A) um dia por vez")
    por_dia, incompletos = {}, []
    for dia in dias:
        d = dia.strftime("%Y%m%d")
        itens, info = pncp.varrer_publicacao(d, d, a.mod, tamanho=50,
                                             pausa=a.pausa)
        ids = {it.get("numeroControlePNCP") for it in itens}
        ids.discard(None)
        por_dia[d] = ids
        marca = "completa" if info.get("completa") else "INCOMPLETA"
        if not info.get("completa"):
            incompletos.append("dia %s (%s)" % (d, info.get("erro") or "páginas"))
        print("     %s  %5d distintos · %3s de %3s páginas · %s"
              % (d, len(ids), info.get("paginas_lidas"),
                 info.get("total_paginas"), marca))
        time.sleep(a.pausa)
    uniao = set().union(*por_dia.values()) if por_dia else set()
    print("     união dos dias ....... %d distintos" % len(uniao))
    print()

    # ------------------------------------------------- B: a janela de uma vez
    print("  B) a janela inteira de uma vez")
    itens_b, info_b = pncp.varrer_publicacao(a.ini, a.fim, a.mod, tamanho=50,
                                             pausa=a.pausa)
    ids_b = {it.get("numeroControlePNCP") for it in itens_b}
    ids_b.discard(None)
    if not info_b.get("completa"):
        incompletos.append("janela inteira (%s)" % (info_b.get("erro") or "páginas"))
    print("     %5d distintos · %s de %s páginas · %s"
          % (len(ids_b), info_b.get("paginas_lidas"), info_b.get("total_paginas"),
             "completa" if info_b.get("completa") else "INCOMPLETA"))
    print()

    # ------------------------------------------------------------- veredito
    so_a, so_b = uniao - ids_b, ids_b - uniao
    print("-" * 96)
    if incompletos:
        print("  ATENÇÃO — alguma varredura ficou incompleta; o veredito é frágil:")
        for x in incompletos:
            print("     · %s" % x)
        print()
    print("  só em A (dia a dia) ...... %d" % len(so_a))
    print("  só em B (janela) ......... %d" % len(so_b))
    perda = (100.0 * len(so_a) / len(uniao)) if uniao else 0.0
    print("  perda da janela larga .... %.1f%%" % perda)
    print()
    print("  o caso nomeado — %s" % CASO_NOME)
    print("     em A (dia a dia) ...... %s" % ("SIM" if CASO in uniao else "não"))
    print("     em B (janela) ......... %s" % ("SIM" if CASO in ids_b else "não"))
    print()
    # TRUNCAR E PERDER, NAO DIFERIR. A primeira versao deste veredito olhava
    # so `so_a` e concluia "trunca" com 4,9%. Mas `so_b` tinha 90 -- a janela
    # larga trouxe MAIS registros que a soma dos dias, nao menos. Um conjunto
    # que ganha e perde itens nos dois sentidos nao esta truncado: esta
    # instavel. Sao diagnosticos diferentes e levam a consertos diferentes.
    if incompletos:
        print("  SEM VEREDITO: alguma varredura ficou incompleta. Repetir.")
    elif len(so_a) == 0 and len(so_b) == 0:
        print("  VEREDITO: os dois caminhos dão o MESMO conjunto.")
        print("  A janela larga não perde nada — o truncamento registrado em")
        print("  23/09 era a página curta, diagnosticada como defeito do")
        print("  servidor.")
    elif len(so_b) == 0:
        print("  VEREDITO: a janela larga TRUNCA — o conjunto dela está CONTIDO")
        print("  no dia a dia e perde %.1f%%. O achado original se confirma."
              % perda)
    else:
        print("  VEREDITO: a janela larga NÃO trunca — ela DIFERE.")
        print("     %d registros só aparecem dia a dia" % len(so_a))
        print("     %d registros só aparecem na janela" % len(so_b))
        print("     %d em comum" % len(uniao & ids_b))
        print()
        print("  Truncar é PERDER. Um conjunto que ganha e perde itens nos dois")
        print("  sentidos não está truncado: está instável — a mesma janela")
        print("  móvel já documentada na busca por palavra, e as páginas curtas")
        print("  caindo em lugares diferentes a cada execução.")
        print()
        print("  Os 86%% registrados em 23/09 NÃO se confirmam: a diferença")
        print("  medida agora é de %.1f%% para um lado e %.1f%% para o outro."
              % (perda, 100.0 * len(so_b) / len(ids_b) if ids_b else 0.0))
        if CASO in uniao and CASO in ids_b:
            print("  E o caso nomeado que sustentava o achado aparece nos DOIS.")

    io.open(DESTINO, "w", encoding="utf-8").write(json.dumps(
        {"medido_em": time.strftime("%Y-%m-%d"), "janela": [a.ini, a.fim],
         "modalidade": a.mod, "dia_a_dia": len(uniao), "janela_inteira": len(ids_b),
         "so_em_dia_a_dia": len(so_a), "so_na_janela": len(so_b),
         "perda_pct": round(perda, 1), "incompletos": incompletos,
         "caso": CASO, "caso_em_dia_a_dia": CASO in uniao,
         "caso_na_janela": CASO in ids_b,
         "por_dia": {d: len(v) for d, v in por_dia.items()}},
        ensure_ascii=False, indent=1))
    print("\n  salvo em saidas/_truncamento_janela.json · custo R$ 0,00")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
