# -*- coding: utf-8 -*-
"""
A página certa estava no top-k do BM25?

    python 46_recall_recuperacao.py [--k 4,6,8,12] [--so <pasta>]

NÃO CHAMA MODELO. Reconstrói o índice BM25 das páginas e replays a seleção.

O QUE ISTO MEDE, E POR QUE É A PERGUNTA QUE FALTAVA
  A [[ADR-010]] escolheu **RAG com BM25** para licitações grandes, em vez de
  mandar o edital inteiro. A decisão foi tomada por custo e cabe defender — mas
  ela cria um risco que a ancoragem **não** detecta:

    Se a página que contém a resposta não entrar no top-k, o modelo nunca a vê.
    Ele então responde "não localizado" — e essa resposta **ancora**, porque
    ausência declarada é aprovada por construção.

  Ou seja: uma falha de RECUPERAÇÃO se disfarça de informação ausente do
  edital. É silenciosa por desenho.

COMO SE MEDE SEM GABARITO HUMANO
  As respostas do acervo já passaram pelo Verificador: quando uma citação é
  APROVADA, o trecho **existe** naquela página. Logo a página citada é, por
  construção, uma página onde a resposta está.

  Então a pergunta vira aritmética: para cada resposta ancorada, a página que
  ela cita estava entre as que o BM25 selecionou para aquela pergunta?

  Não é recall contra verdade absoluta — se houver DUAS páginas com a resposta
  e o BM25 trouxer a outra, conta como acerto, e está certo contar. É recall
  contra "o modelo conseguiu responder com o que recebeu".
"""
from __future__ import annotations

import argparse
import glob
import io
import json
import os
import sys
import time

AQUI = os.path.dirname(os.path.abspath(__file__))
RAIZ = os.path.dirname(AQUI)
AMOSTRAS = os.path.join(RAIZ, "amostras")
SAIDAS = os.path.join(RAIZ, "saidas")
sys.path.insert(0, AQUI)

from fopa import extrator, questionario                           # noqa: E402
from fopa import recuperacao as rec                               # noqa: E402

DESTINO = os.path.join(SAIDAS, "_recall_recuperacao.json")


# O k que o extrator usa de verdade (`fopa/extrator.py`, parametro `k_rag`).
# As perdas que interessam sao as DESTE k, nao as do maior que se testa.
K_PADRAO = 6


def _norm_simples(t: str) -> str:
    import re
    import unicodedata
    t = unicodedata.normalize("NFKD", (t or "").lower())
    t = "".join(c for c in t if not unicodedata.combining(c))
    return re.sub(r"[^a-z0-9 ]+", " ", t)


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--k", default="4,6,8,12")
    ap.add_argument("--so", default=None)
    a = ap.parse_args()
    ks = [int(x) for x in a.k.split(",") if x.strip()]

    try:
        sys.stdout.reconfigure(line_buffering=True)
    except AttributeError:
        pass

    por_id = {p.id: p for p in questionario.PERGUNTAS}
    sempre = getattr(extrator, "SEMPRE_INCLUIR", ())

    print("=" * 84)
    print("  RECALL DA RECUPERAÇÃO — a página citada estava no top-k?")
    print("=" * 84)

    placar = {k: {"acertos": 0, "perdas": 0} for k in ks}
    perdidas = []
    linhas = []

    for f in sorted(glob.glob(os.path.join(SAIDAS, "*", "auditoria.json"))):
        pasta = os.path.basename(os.path.dirname(f))
        if a.so and a.so.lower() not in pasta.lower():
            continue
        d = json.load(io.open(f, encoding="utf-8"))
        origem = d.get("licitacao") or pasta
        dir_pasta = os.path.join(AMOSTRAS, origem)
        if not os.path.isdir(dir_pasta):
            continue

        # Só vale medir onde o RAG foi usado: em contexto completo o modelo
        # recebe tudo, e o recall é 100% por definição.
        if (d.get("modo") or "") != "rag":
            print("  %-46s (modo %s — recall não se aplica)"
                  % (pasta[:46], d.get("modo")))
            continue

        try:
            paginas = extrator.carregar_paginas(dir_pasta)
        except Exception as e:                                    # noqa: BLE001
            print("  %-46s ERRO ao reler páginas: %s" % (pasta[:46], str(e)[:30]))
            continue
        indice = rec.IndiceBM25(paginas)

        ancoradas = [r for r in d.get("respostas", [])
                     if r.get("veredito") == "APROVADO"
                     and r.get("arquivo") and r.get("pagina")
                     and (r.get("trecho_literal") or "").strip()]
        if not ancoradas:
            continue

        dest = {k: 0 for k in ks}
        for r in ancoradas:
            p = por_id.get(r["id"])
            if p is None:
                continue
            alvo = (r["arquivo"], r["pagina"])
            for k in ks:
                sel = {(x.arquivo, x.numero)
                       for x in rec.paginas_para_pergunta(indice, p, k=k,
                                                          sempre=sempre)}
                if alvo in sel:
                    placar[k]["acertos"] += 1
                    dest[k] += 1
                else:
                    placar[k]["perdas"] += 1
                    # REGISTRAR A PERDA NO k QUE A PRODUCAO USA, nao no maior.
                    #
                    # Ate 23/09/2026 a lista so guardava perdas em `max(ks)` --
                    # k=12, onde o recall e 100%. Resultado: a lista saia SEMPRE
                    # VAZIA, e o relatorio dava a impressao de que nao havia o
                    # que investigar. As perdas que importam sao as do k=6, que
                    # e o padrao do extrator: sao elas que viram "nao
                    # localizado" em producao, e "nao localizado" ANCORA.
                    if k == K_PADRAO:
                        perdidas.append({"pasta": pasta, "id": r["id"],
                                         "arquivo": r["arquivo"],
                                         "pagina": r["pagina"],
                                         "k": k,
                                         "pergunta": (r.get("pergunta") or "")[:70],
                                         "trecho": (r.get("trecho_literal")
                                                    or r.get("trecho") or "")[:400],
                                         "termos_da_pergunta": list(
                                             getattr(p, "termos", []) or [])})

        linha = "  %-46s %3d ancoradas · " % (pasta[:46], len(ancoradas))
        linha += " · ".join("k=%d %d/%d" % (k, dest[k], len(ancoradas)) for k in ks)
        print(linha)
        linhas.append({"pasta": pasta, "ancoradas": len(ancoradas),
                       "por_k": {str(k): dest[k] for k in ks}})

    print()
    print("  %-6s %8s %8s %8s" % ("k", "acertos", "perdas", "recall"))
    print("  " + "-" * 34)
    for k in ks:
        ac, pe = placar[k]["acertos"], placar[k]["perdas"]
        tot = ac + pe
        print("  k=%-4d %8d %8d %7.1f%%"
              % (k, ac, pe, 100.0 * ac / tot if tot else 0))

    # ---------------------------------------------- o passo que a ADR-010 pediu
    # "Cada resposta ancorada cujo trecho NAO contem nenhum termo-sinal da sua
    # pergunta e um candidato a termo faltando. O 46 ja lista as perdidas;
    # transformá-las em sugestao de vocabulario e o passo seguinte, e e
    # barato." -- ADR-010. E o passo seguinte e este bloco.
    if perdidas:
        print()
        print("  VOCABULÁRIO CANDIDATO — o que o trecho diz e a pergunta não pede")
        print("  " + "-" * 82)
        for x in perdidas:
            tr = _norm_simples(x.get("trecho") or "")
            termos = {_norm_simples(t) for t in x.get("termos_da_pergunta") or []}
            palavras = [w for w in tr.split()
                        if len(w) >= 5 and w not in termos and not w.isdigit()]
            # o que aparece no trecho e em nenhum termo-sinal da pergunta
            vistos, sugestao = set(), []
            for w in palavras:
                if w in vistos:
                    continue
                vistos.add(w)
                sugestao.append(w)
            print("     %s · %s" % (x["id"], x["pasta"][:44]))
            print("        pergunta pede: %s" % (", ".join(
                sorted(x.get("termos_da_pergunta") or [])) or "(sem termos-sinal)"))
            print("        trecho traz .: %s" % (", ".join(sugestao[:12]) or "(vazio)"))
        print()
        print("  Nem toda palavra acima é termo — é matéria-prima para escolher.")
        print("  A regra da ADR-010: a lista tem que carregar o vocabulário do")
        print("  EDITAL, não o do analista.")

    if perdidas:
        print("\n  PERDIDAS mesmo no maior k — a página citada não foi selecionada:")
        for x in perdidas[:12]:
            print("   %-40s %-5s %s p.%s"
                  % (x["pasta"][:40], x["id"], x["arquivo"][:28], x["pagina"]))
        print("\n  Estas são o caso que a ancoragem NÃO pega: se o modelo não")
        print("  tivesse acertado apesar do BM25, teria dito 'não localizado'")
        print("  e essa resposta seria aprovada como ausência legítima.")

    json.dump({"medido_em": time.strftime("%Y-%m-%dT%H:%M:%S%z"),
               "k": ks, "placar": {str(k): placar[k] for k in ks},
               "por_licitacao": linhas, "perdidas": perdidas},
              io.open(DESTINO, "w", encoding="utf-8"), ensure_ascii=False, indent=1)
    print("\n  salvo: %s" % os.path.relpath(DESTINO, RAIZ))
    print("  custo em API de modelo: R$ 0,00")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
