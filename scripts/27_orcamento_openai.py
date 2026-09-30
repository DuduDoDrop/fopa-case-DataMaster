# -*- coding: utf-8 -*-
"""
Orçamento de tokens ANTES de gastar — conta local, sem chamar API.

    python 27_orcamento_openai.py "<pasta>" ["<pasta>" ...]
    python 27_orcamento_openai.py --todas

POR QUE ISTO EXISTE
  Porque "quanto vai custar?" é uma pergunta que se responde antes, não depois.
  O preço por milhão de tokens vem da tabela do fornecedor; a QUANTIDADE de
  tokens é propriedade dos documentos, e ela pode ser medida aqui, de graça,
  com o mesmo tokenizador que o modelo usa.

  A ocasião foi prosaica: a conta OpenAI estava sem crédito e a pergunta virou
  "quanto é preciso pôr?". Mas o número serve para qualquer decisão de custo —
  escolher entre contexto completo e RAG, dimensionar um lote, defender a conta.

O QUE ELE CONTA, E O QUE NÃO CONTA
  Conta a ENTRADA: o contexto exato que `extrator.montar_mensagem` montaria,
  lote a lote, mais a instrução de sistema. É a parcela que domina — 76% a 86%
  do custo nas medições com Claude (ver [[Resultados medidos]]).

  NÃO conta a saída, porque ela não é mensurável antes: depende de quanto o
  modelo escreve e de quantos tokens de raciocínio ele gasta, e chutar isso
  seria inventar número. O relatório mostra a saída como faixa, calculada a
  partir do que as extrações com Claude de fato produziram nesta amostra.
"""
from __future__ import annotations

import argparse
import glob
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

from fopa import extrator, modelos, recuperacao as rec                # noqa: E402
from fopa.questionario import PERGUNTAS, POR_ID, instrucao_sistema     # noqa: E402

AMOSTRAS = os.path.join(RAIZ, "amostras")

# Saída observada nas extrações reais desta amostra com Claude. Não é previsão
# para o OpenAI — é a ordem de grandeza da tarefa, que é o que se pode afirmar.
SAIDA_OBSERVADA = (3_000, 9_000)


def barra(t: str) -> None:
    print("\n" + "=" * 92 + "\n  %s\n" % t + "=" * 92)


def contar(texto: str, enc) -> int:
    return len(enc.encode(texto, disallowed_special=()))


def orcar(pasta: str, enc, lote: int = 6, k_rag: int = 6) -> dict | None:
    nome = os.path.basename(pasta.rstrip("\\/"))
    try:
        paginas = extrator.carregar_paginas(pasta)
    except Exception as e:                                            # noqa: BLE001
        print("  %-52s FALHOU: %s" % (nome[:52], e))
        return None
    if not paginas:
        print("  %-52s sem páginas legíveis" % nome[:52])
        return None

    # Monta o contexto pelo MESMO caminho do extrator (`rec.montar_contexto`,
    # `SEMPRE_INCLUIR`, ordem de precedência). Um orçamento que monta o contexto
    # do seu próprio jeito orça outra coisa, e a diferença só aparece na fatura.
    completo = rec.montar_contexto(paginas)
    modo = rec.escolher_modo(paginas)

    ids = [p.id for p in PERGUNTAS]
    lotes = [ids[i:i + lote] for i in range(0, len(ids), lote)]
    indice = rec.IndiceBM25(paginas) if modo == "rag" else None

    total = 0
    for grupo in lotes:
        if modo == "rag":
            escolhidas: dict[tuple[str, int], rec.Pagina] = {}
            for pid in grupo:
                for pg in rec.paginas_para_pergunta(indice, POR_ID[pid], k=k_rag,
                                                    sempre=extrator.SEMPRE_INCLUIR):
                    escolhidas[(pg.arquivo, pg.numero)] = pg
            contexto = rec.montar_contexto(sorted(
                escolhidas.values(),
                key=lambda x: (extrator._ordem_precedencia(x.arquivo),
                               x.arquivo, x.numero)))
        else:
            contexto = completo
        total += contar(instrucao_sistema(), enc)
        total += contar(extrator.montar_mensagem(contexto, grupo, nome), enc)

    print("  %-52s %-18s %2d req  %10s tok"
          % (nome[:52], modo, len(lotes), f"{total:,}".replace(",", ".")))
    return {"nome": nome, "modo": modo, "requisicoes": len(lotes),
            "entrada": total, "paginas": len(paginas)}


def main() -> int:
    ap = argparse.ArgumentParser(description="Orça tokens de entrada, sem chamar API")
    ap.add_argument("pastas", nargs="*", help="pastas em amostras/")
    ap.add_argument("--todas", action="store_true")
    ap.add_argument("--lote", type=int, default=6)
    ap.add_argument("--k", type=int, default=6)
    a = ap.parse_args()

    import tiktoken
    # o200k_base é a codificação da família GPT-4o/5. Se o modelo configurado não
    # for reconhecido pelo tiktoken instalado, cair nela é melhor que falhar: a
    # contagem fica aproximada, e o relatório diz que ficou.
    try:
        enc = tiktoken.encoding_for_model(modelos.MODELO_OPENAI)
        exato = True
    except KeyError:
        enc = tiktoken.get_encoding("o200k_base")
        exato = False

    if a.todas:
        alvos = sorted(d for d in glob.glob(os.path.join(AMOSTRAS, "*"))
                       if os.path.isdir(d) and not os.path.basename(d).startswith("_"))
    else:
        alvos = [p if os.path.isdir(p) else os.path.join(AMOSTRAS, p) for p in a.pastas]
    if not alvos:
        print("  informe ao menos uma pasta, ou use --todas")
        return 2

    barra("ORÇAMENTO DE ENTRADA — %s%s"
          % (modelos.MODELO_OPENAI,
             "" if exato else "  (tokenizador aproximado: o200k_base)"))
    print("  lote de %d perguntas por requisição, k=%d na recuperação\n" % (a.lote, a.k))

    linhas = [r for r in (orcar(p, enc, a.lote, a.k) for p in alvos) if r]
    if not linhas:
        return 1

    entrada = sum(r["entrada"] for r in linhas)
    reqs = sum(r["requisicoes"] for r in linhas)

    print("\n" + "-" * 92)
    print("  %d licitação(ões) · %d requisições · entrada %s tokens"
          % (len(linhas), reqs, f"{entrada:,}".replace(",", ".")))
    print("  saída estimada: %s a %s tokens por licitação, pela ordem de grandeza"
          % tuple(f"{n:,}".replace(",", ".") for n in SAIDA_OBSERVADA))
    print("     (observada nas extrações com Claude nesta mesma amostra; não é")
    print("      previsão para o OpenAI — token de raciocínio é imprevisível)")

    pe = os.environ.get("FOPA_PRECO_OPENAI_ENTRADA")
    ps = os.environ.get("FOPA_PRECO_OPENAI_SAIDA")
    print("\n" + "-" * 92)
    if pe:
        e_usd = entrada * float(pe) / 1_000_000
        s_lo = len(linhas) * SAIDA_OBSERVADA[0] * float(ps or pe) / 1_000_000
        s_hi = len(linhas) * SAIDA_OBSERVADA[1] * float(ps or pe) / 1_000_000
        print("  CUSTO: US$ %.4f de entrada + US$ %.4f a %.4f de saída"
              % (e_usd, s_lo, s_hi))
        print("         US$ %.4f a %.4f no total  (R$ %.2f a %.2f)"
              % (e_usd + s_lo, e_usd + s_hi,
                 (e_usd + s_lo) * modelos.USD_BRL, (e_usd + s_hi) * modelos.USD_BRL))
    else:
        print("  Sem preço configurado, não há custo a exibir — e um número")
        print("  inventado aqui contaminaria planilha, benchmark e defesa.")
        print("  Pegue a tabela oficial do fornecedor e preencha no .env:")
        print("      FOPA_PRECO_OPENAI_ENTRADA=<USD por milhão de tokens>")
        print("      FOPA_PRECO_OPENAI_SAIDA=<USD por milhão de tokens>")
        print("  Depois rode este script de novo: ele multiplica e mostra o total.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
