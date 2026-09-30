# -*- coding: utf-8 -*-
"""
Procura o invariante: existe algo escrito em TODA licitação de folha?

    python 25_invariante.py

Custo R$ 0,00. Lê `saidas/_corpus_escopo.json` (coletado por `24_corpus_escopo.py`)
e os objetos das licitações confirmadas em disco.

A PERGUNTA
Um filtro feito de várias regras acerta até encontrar o caso que nenhuma cobre.
Um filtro feito de um invariante — uma expressão que aparece em todas as de
folha e em nenhuma das outras — erra muito menos, e falha de forma previsível.

Este script mede, termo a termo:

    cobertura   quantos dos objetos DE FOLHA contêm o termo
    precisão    dos que contêm o termo, quantos são de folha

O invariante perfeito teria cobertura 100% e precisão 100%. Ele provavelmente
não existe, porque cada município redige como quer — mas medir mostra o quanto
se chega perto, e quais termos valem como âncora e quais só somam ruído.

O QUE ESTE SCRIPT NÃO FAZ
Não usa o próprio filtro como gabarito, o que seria circular. O rótulo vem de
duas fontes independentes: as 12 licitações confirmadas em disco (lidas e
extraídas) e o julgamento registrado em `_catalogo_escopo.json`, que é onde os
casos conferidos à mão ficam guardados.
"""
from __future__ import annotations

import collections
import glob
import json
import os
import re
import sys
import unicodedata

for _f in (sys.stdout, sys.stderr):
    try:
        _f.reconfigure(encoding="utf-8", errors="replace")
    except (AttributeError, ValueError):
        pass

AQUI = os.path.dirname(os.path.abspath(__file__))
RAIZ = os.path.dirname(AQUI)
sys.path.insert(0, AQUI)

SAIDAS = os.path.join(RAIZ, "saidas")
CORPUS = os.path.join(SAIDAS, "_corpus_escopo.json")
CATALOGO = os.path.join(SAIDAS, "_catalogo_escopo.json")

# Candidatos a invariante, tirados da leitura dos objetos reais.
CANDIDATOS = [
    ("folha de pagamento", r"folha\s+de\s+pagamento"),
    ("folha (qualquer forma)", r"folha\s+d[eoa]s?\s+\w+|folha\s+salarial"),
    ("instituição financeira", r"institui[çc][ãa]o\s+financeira"),
    ("banco / bancário", r"\bbanco\b|banc[áa]ri"),
    ("cessão onerosa", r"cess[ãa]o\s+onerosa"),
    ("exclusividade", r"exclusividade"),
    ("servidores", r"servidor(?:es)?\s+p[úu]blic|servidores\s+(?:ativos|municipais)"),
    ("crédito(s) da folha", r"cr[ée]ditos?\s+(?:provenientes\s+)?d[ao]\s+folha"),
    ("processamento/gerenciamento da folha",
     r"(?:processamento|gerenciamento|gest[ãa]o|administra[çc][ãa]o)\s+"
     r"(?:,?\s*\w+\s+){0,3}?d[ao]\s+folha"),
    ("pagamento dos servidores", r"pagamento\s+d[oa]s\s+servidores"),
    ("BACEN / Banco Central", r"banco\s+central|bacen"),
    ("consignado (sinal NEGATIVO)", r"consigna"),
    ("sistema/software (NEGATIVO)", r"software|sistema\s+|plataforma"),
    ("contratação de empresa (NEGATIVO)", r"contrata[çc][ãa]o\s+de\s+empresa"),
]


def norm(s: str) -> str:
    s = unicodedata.normalize("NFKD", s or "").encode("ascii", "ignore").decode()
    return re.sub(r"\s+", " ", s.lower()).strip()


def objetos_confirmados() -> list[tuple[str, bool]]:
    """(objeto, é de folha) das licitações lidas e extraídas em disco."""
    saida = []
    for f in sorted(glob.glob(os.path.join(SAIDAS, "*", "auditoria.json"))):
        d = json.load(open(f, encoding="utf-8"))
        q2 = next((r for r in d.get("respostas", []) if r["id"] == "Q2"), None)
        if q2 and q2.get("resposta"):
            saida.append((q2["resposta"], True))   # as 12 em disco são do escopo
    return saida


def do_catalogo() -> list[tuple[str, bool]]:
    """Casos julgados à mão e registrados. Vazio se o catálogo não existe."""
    if not os.path.isfile(CATALOGO):
        return []
    d = json.load(open(CATALOGO, encoding="utf-8"))
    return [(c["objeto"], c["e_folha"]) for c in d.get("casos", [])]


def main() -> int:
    rotulados = objetos_confirmados() + do_catalogo()
    if not rotulados:
        print("sem material rotulado. Rode as extrações ou preencha o catálogo.")
        return 2

    dentro = [o for o, v in rotulados if v]
    fora = [o for o, v in rotulados if not v]

    print("=" * 100)
    print("  PROCURA DO INVARIANTE — o que aparece em TODA licitação de folha?")
    print("=" * 100)
    print("  %d objetos julgados: %d de folha, %d fora\n" % (len(rotulados), len(dentro), len(fora)))

    print("  %-40s %10s %10s %s" % ("termo", "cobertura", "precisão", "veredito"))
    print("  " + "-" * 92)

    for rotulo, padrao in CANDIDATOS:
        rx = re.compile(padrao, re.I)
        em_dentro = sum(1 for o in dentro if rx.search(norm(o)))
        em_fora = sum(1 for o in fora if rx.search(norm(o)))
        cob = 100.0 * em_dentro / max(len(dentro), 1)
        prec = 100.0 * em_dentro / max(em_dentro + em_fora, 1) if (em_dentro + em_fora) else 0.0

        # SINAL NEGATIVO SE LE AO CONTRARIO — e por muito tempo nao se lia.
        #
        # Para um termo positivo, cobertura alta e bom. Para um NEGATIVO, o que
        # se quer e cobertura BAIXA (quase nunca aparece em licitacao de folha)
        # e presenca alta do lado de fora.
        #
        # Com a regra unica, `sistema/software` saiu rotulado "parcial" com 0%
        # de cobertura — sendo que 0% e a NOTA MAXIMA para um excludente: o
        # termo nunca aparece numa licitacao de folha, entao excluir por ele
        # nunca descarta nada legitimo. O melhor discriminador da tabela estava
        # marcado como mediano, e a tabela existe justamente para escolher
        # discriminadores.
        #
        # Duas escalas lidas com uma regra so devolvem a leitura de uma delas.
        negativo = "NEGATIVO" in rotulo
        if negativo:
            fora_pct = 100.0 * em_fora / max(len(fora), 1)
            if cob == 0 and em_fora:
                veredito = ("EXCLUDENTE SEGURO — nunca aparece em folha, "
                            "e em %.0f%% do que está fora" % fora_pct)
            elif cob == 0:
                veredito = "inútil — não aparece em lugar nenhum"
            elif prec <= 20:
                veredito = ("bom excludente — quando aparece, %.0f%% das vezes "
                            "NÃO é folha" % (100 - prec))
            else:
                veredito = ("PERIGOSO — excluiria %.0f%% das licitações de "
                            "folha" % cob)
        elif cob == 100 and prec == 100:
            veredito = "INVARIANTE — cobre tudo e não erra"
        elif cob == 100:
            veredito = "necessário, não suficiente (aparece fora também)"
        elif prec == 100 and em_dentro:
            veredito = "suficiente, não necessário (quando aparece, é folha)"
        else:
            veredito = "parcial"
        print("  %-40s %8.0f%% %9.0f%% %s" % (rotulo[:40], cob, prec, veredito))

    # ------------------------------------------------- o que falta cobrir
    print("\n  " + "-" * 92)
    print("  Objetos de folha que NÃO contêm 'folha de pagamento' literal:")
    rx = re.compile(r"folha\s+de\s+pagamento", re.I)
    faltantes = [o for o in dentro if not rx.search(norm(o))]
    if faltantes:
        for o in faltantes:
            print("    %s" % o[:150].replace("\n", " "))
    else:
        print("    nenhum — todos dizem 'folha de pagamento'")

    print("\n  custo em API: R$ 0,00")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
