# -*- coding: utf-8 -*-
"""
A fila de rotulagem humana do filtro de escopo — onde ele está mais frágil.

    python 62_fila_rotulagem.py [--n 40]

NAO CHAMA MODELO. NAO CHAMA REDE. Le o corpus e o catalogo humano em disco.

O ITEM QUE ISTO FECHA (a metade que e codigo)
  `Vocabulario de busca` e `2 Classificador` pedem, ha dias: "toda decisao
  REVISAR julgada por humano vira exemplo rotulado" e "a cada 50 decisoes,
  revisar se algum termo novo apareceu". Nunca houve a FILA -- o processo
  existia no papel e nao tinha de onde tirar os casos. Este script faz a fila.
  Julgar continua sendo humano.

POR QUE NAO E "SORTEAR 40 DO CORPUS"
  Amostra aleatoria de 1.518 registros gasta o julgamento humano em casos
  obvios. O catalogo de 23 casos existe justamente porque um filtro validado
  por ele mesmo nao vale nada -- entao cada caso julgado e caro e precisa
  cair onde o filtro esta FRAGIL.

  A fragilidade nao e uniforme, e da para ler no proprio motivo da decisao:

    aceitos por evidencia POSITIVA (455 + 156)
        "contrata a operacao da folha", "cessao onerosa do direito de pagar"
        -- o objeto diz o que o filtro precisa ouvir. Risco baixo.

    aceitos por AUSENCIA de sinal negativo (58)
        "contrata instituicao financeira, e nada indica consignado"
        -- o filtro aceita porque NAO achou motivo para recusar. E a unica
        regra do conjunto que decide por falta de prova.

    aceito por objeto CURTO DEMAIS (1)
        passa para revisao de proposito, e ninguem revisou ainda.

    rejeitados que FALAM de folha (34 + 206)
        "fala de folha, mas nao e a operacao dela", "sistema ou plataforma"
        -- e aqui que mora o falso negativo. A varredura de recall ja achou
        cinco assim, um deles com 2.210 servidores.

  A fila sai dessas quatro faixas, e nao das duas primeiras.

O QUE O ARQUIVO DE SAIDA TEM
  Um JSON com `veredito: null` em cada caso, para ser preenchido a mao com
  `dentro` ou `fora`, mais `por_que`. Preenchido, ele vira insumo do
  `_catalogo_escopo.json` -- que e o gabarito independente da suite do filtro.
"""
from __future__ import annotations

import argparse
import io
import json
import os
import sys
import time
import unicodedata

AQUI = os.path.dirname(os.path.abspath(__file__))
RAIZ = os.path.dirname(AQUI)
sys.path.insert(0, AQUI)

CORPUS = os.path.join(RAIZ, "saidas", "_corpus_escopo.json")
CATALOGO = os.path.join(RAIZ, "saidas", "_catalogo_escopo.json")
DESTINO = os.path.join(RAIZ, "saidas", "_fila_rotulagem.json")

# As faixas fracas, com a razao de cada uma estar aqui.
FAIXAS = [
    ("aceito sem sinal positivo", True,
     ("nada indica consignado",),
     "aceita por AUSÊNCIA de sinal negativo — a única regra que decide por "
     "falta de prova"),
    ("aceito sem poder decidir", True,
     ("curto demais",),
     "o objeto não dá para decidir; passa para revisão de propósito"),
    ("rejeitado falando de folha", False,
     ("fala de folha, mas não é a operação dela",),
     "o objeto fala de folha e foi recusado — é onde mora o falso negativo"),
    ("rejeitado como sistema", False,
     ("sistema ou plataforma que opera sobre a folha",),
     "a fronteira mais fina do critério: operar a folha × vender o sistema"),
]


def _norm(t: str) -> str:
    t = unicodedata.normalize("NFKD", (t or "").lower())
    return "".join(c for c in t if not unicodedata.combining(c))


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--n", type=int, default=40,
                    help="quantos casos por faixa, no máximo")
    a = ap.parse_args()
    try:
        sys.stdout.reconfigure(line_buffering=True, encoding="utf-8")
    except (AttributeError, ValueError):
        pass

    if not os.path.isfile(CORPUS):
        print("falta saidas/_corpus_escopo.json — rode `24_corpus_escopo.py`.")
        return 1
    regs = json.load(io.open(CORPUS, encoding="utf-8"))["registros"]
    regs = list(regs.values()) if isinstance(regs, dict) else regs

    ja_julgados = set()
    if os.path.isfile(CATALOGO):
        cat = json.load(io.open(CATALOGO, encoding="utf-8"))
        ja_julgados = {c.get("controle") for c in (cat.get("casos") or [])}

    print("=" * 96)
    print("  FILA DE ROTULAGEM — onde o filtro de escopo está mais frágil")
    print("  corpus: %d registros · catálogo humano: %d já julgados"
          % (len(regs), len(ja_julgados)))
    print("=" * 96)
    print()

    fila, resumo = [], []
    for nome, dentro, chaves, porque in FAIXAS:
        candidatos = [
            r for r in regs
            if bool(r.get("dentro")) is dentro
            and any(_norm(k) in _norm(r.get("motivo")) for k in chaves)
            and r.get("controle") not in ja_julgados
        ]
        # os maiores objetos primeiro: texto curto demais nao ensina nada,
        # e o julgamento humano rende mais onde ha o que ler
        candidatos.sort(key=lambda r: -len(r.get("objeto") or ""))
        escolhidos = candidatos[:a.n]
        print("  %-30s %4d candidato(s) · %d na fila" %
              (nome, len(candidatos), len(escolhidos)))
        print("     %s" % porque)
        for r in escolhidos:
            fila.append({
                "faixa": nome,
                "o_filtro_disse": "dentro" if dentro else "fora",
                "motivo_do_filtro": r.get("motivo"),
                "controle": r.get("controle"),
                "orgao": r.get("orgao"),
                "uf": r.get("uf"),
                "municipio": r.get("municipio"),
                "modalidade": r.get("modalidade"),
                "objeto": r.get("objeto"),
                "veredito": None,          # preencher: "dentro" ou "fora"
                "por_que": None,           # preencher: uma linha, por favor
            })
        resumo.append({"faixa": nome, "candidatos": len(candidatos),
                       "na_fila": len(escolhidos), "por_que_esta_aqui": porque})
        print()

    print("-" * 96)
    print("  %d caso(s) na fila, de %d candidatos nas faixas frágeis."
          % (len(fila), sum(x["candidatos"] for x in resumo)))
    print()
    print("  O QUE **NÃO** ESTÁ AQUI, e por quê")
    pos = sum(1 for r in regs if r.get("dentro")
              and not any(_norm(k) in _norm(r.get("motivo"))
                          for _, d, ks, _ in FAIXAS if d for k in ks))
    print("     %d aceitos por evidência POSITIVA — o objeto diz o que o filtro" % pos)
    print("     precisa ouvir (\"contrata a operação da folha\", \"cessão onerosa\").")
    print("     Julgar esses gasta atenção humana em caso óbvio.")
    print()
    print("  COMO USAR")
    print("     1. abra `saidas/_fila_rotulagem.json`")
    print("     2. preencha `veredito` com \"dentro\" ou \"fora\", e `por_que`")
    print("     3. os que DIVERGIREM do filtro são os que valem: cada um é")
    print("        um caso novo para o `_catalogo_escopo.json` e um teste novo")
    print("        para o `23_testa_escopo.py`")
    print()
    print("  O catálogo é a única fonte independente do filtro. Um filtro")
    print("  validado por ele mesmo não vale nada — por isso a fila sai daqui")
    print("  e o julgamento não é meu.")

    io.open(DESTINO, "w", encoding="utf-8").write(json.dumps(
        {"gerado_em": time.strftime("%Y-%m-%d"),
         "proposito": ("Casos em que o filtro de escopo está mais frágil, "
                       "para julgamento humano. Preencher `veredito` e "
                       "`por_que`; os que divergirem do filtro viram caso do "
                       "_catalogo_escopo.json."),
         "corpus": len(regs), "ja_julgados": len(ja_julgados),
         "faixas": resumo, "casos": fila},
        ensure_ascii=False, indent=1))
    print("\n  salvo em saidas/_fila_rotulagem.json · custo R$ 0,00")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
