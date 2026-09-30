---
tipo: decisao
familia: decisoes
adr: 10
data: 2026-09-22
decisao: aceita
status: verificado
atualizado: 2026-09-28
tags: [decisao, rag, bm25, custo, nucleo]
---

# ADR-010 — RAG vs contexto completo

> [!abstract] Em uma frase
> A estratégia de uso do modelo é **híbrida com política explícita**: até 180.000 caracteres o modelo lê **tudo**; acima disso, recebe as páginas recuperadas por **BM25** — 12 por pergunta, sempre com os avisos de retificação —; embeddings e fine-tuning foram avaliados e descartados, com motivo e gatilho de reabertura.

## Problema

O case pede uma estratégia de uso ou ajuste de modelos (RAG, fine-tuning ou outra). Os documentos variam de 1 arquivo com 13 páginas a 9 arquivos com 115 — e, depois do OCR de anexos, podem passar de centenas de milhares de tokens.

## Opções

| Opção | Avaliação |
|---|---|
| só contexto completo | não escala e reenvia documentos enormes a cada lote |
| só RAG | em conjunto pequeno é risco puro: o recuperador pode esconder a resposta que caberia inteira |
| embeddings + banco vetorial | custo, dependência externa e documento saindo do servidor para resolver paráfrase que o domínio quase não tem |
| recorte por parágrafo | perderia a página física, que é a unidade de citação |
| fine-tuning | sem volume rotulado; trata forma quando o problema é evidência |
| **híbrido por tamanho, BM25 por página, âncoras forçadas** | auditável, local, medido |

## O que foi medido

| Medida | Resultado |
|---|---|
| mesmo edital, mesmo modelo, só muda o modo | RAG: **−45% de entrada, −36% de custo, a mesma acurácia (17/17, 7/7)** — e um conflito a menos |
| a licitação maior custou menos | Bertioga (115 páginas, RAG) R$ 2,91 contra Pirapó (38 páginas, contexto completo) R$ 4,79 |
| recall por páginas por pergunta (Bertioga) | 87,8% com 4; 95,9% com 6 e com 8; **100% com 12** (79% do documento) |
| termos-sinal revisados contra o corpus | dez termos mortos trocados; perdas da Q7 e da Q10 fechadas com palavras tiradas do próprio edital |

## Escolha

- `escolher_modo`: **contexto completo até 180.000 caracteres**; RAG acima — uma regra de tamanho, gravada na execução.
- **BM25 Okapi** local (k1 = 1,5; b = 0,75), por **página**, com consulta = pergunta + termos-sinal.
- **12 páginas por pergunta** em produção (`db/026`, 24/09/2026): 100% de recall em todas as medições; a página que o RAG perde vira "não localizado", que vai para revisão.
- **Arquivos-âncora sempre incluídos** (retificação, suspensão, comunicado, redesignação, errata, aviso): recuperação estatística não conhece precedência documental.

## O que custa

- Dois caminhos de código para manter e testar.
- O BM25 não resolve paráfrase — mitigado pela curadoria de termos, medida.
- No RAG, conflitos entre documentos podem ficar fora do contexto de uma pergunta; por isso o contexto completo é o padrão enquanto cabe.
- O ganho real do RAG no ponto seguro é de ~21% do documento, não de ordens de grandeza.

## Onde vive em produção

`scripts/fopa/recuperacao.py` e `extrator._paginas_do_lote`, chamados pelo worker no `POST /prompt` e no `POST /reforco`; `configuracao.k_rag = 12`; o modo aparece no detalhe de cada licitação. Detalhe completo em [[RAG com BM25]].

## O que reabriria a decisão

- **Embeddings:** editais descrevendo a mesma exigência com vocabulário que a curadoria de termos não alcance.
- **Fine-tuning:** ao menos 500 editais com gabarito humano **e** o gargalo medido ser custo, não acurácia.

## Relacionadas

[[MOC Decisões]] · [[RAG com BM25]] · [[Questionário — as 17 perguntas]] · [[Técnicas avaliadas e descartadas]] · [[Cache de prompt e ordem do prompt]] · [[ADR-024 Best-of-N e documentos antes das perguntas]]
