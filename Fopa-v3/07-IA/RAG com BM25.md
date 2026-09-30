---
tipo: tecnica
familia: ia
status: verificado
atualizado: 2026-09-28
fonte_codigo:
  - scripts/fopa/recuperacao.py
  - scripts/fopa/extrator.py
  - scripts/fopa/questionario.py
  - api/extracao.py
  - db/026_k_rag_12.sql
tags: [ia, rag, bm25, recuperacao, custo, nucleo]
---

# RAG com BM25

> [!abstract] Em uma frase
> Quando a licitação é pequena, o modelo lê **todos** os documentos; quando passa de **180.000 caracteres**, a solução recupera, para cada pergunta, as **12 páginas** mais relevantes com **BM25** (busca léxica local, sem embeddings), sempre acrescentando os avisos de retificação, suspensão e errata — e a escolha do modo é uma regra de tamanho, auditável, não uma intuição.

## Papel na solução

É a resposta da solução ao item do case "estratégia de uso ou ajuste de modelos (RAG, fine-tuning ou outro)". A estratégia é **híbrida com política explícita**: contexto completo quando cabe (sem risco de o recuperador esconder a resposta) e RAG quando o conjunto cresce (anexos escaneados, depois do OCR, chegam a centenas de milhares de tokens). O modo escolhido fica gravado na execução e aparece no detalhe da licitação.

## A política de modo

```python
LIMITE_CONTEXTO_COMPLETO = 180_000   # caracteres (~50 mil tokens)

def escolher_modo(paginas, forcado=None):
    if forcado:
        return forcado
    total = sum(len(p.texto) for p in paginas)
    return "contexto-completo" if total <= LIMITE_CONTEXTO_COMPLETO else "rag"
```

| Situação | Modo | O que vai em cada lote |
|---|---|---|
| até 180.000 caracteres de texto lido | **contexto completo** | todas as páginas, em ordem de precedência documental |
| acima de 180.000 caracteres | **RAG** | as páginas recuperadas para as 6 perguntas do lote (até 12 por pergunta, unidas) mais as páginas dos arquivos-âncora |

Na licitação de Itapecuru Mirim/MA (28/09/2026), 60 páginas couberam no limite e a extração rodou em contexto completo.

## Como a recuperação funciona

1. **Unidade = página.** O índice é feito por página física, nunca por parágrafo ou por pedaço de tamanho fixo: a página é a unidade de citação obrigatória ([[ADR-005 Info é arquivo mais página física]]). Recortar por parágrafo perderia a página.
2. **Tokenização.** O texto é normalizado (sem acentos, minúsculo), quebrado em palavras de letras e dígitos, e descartam-se palavras de até 2 letras e uma lista de **palavras vazias** do português somada ao ruído jurídico que aparece em toda página ("art", "artigo", "inciso", "parágrafo", "alínea", "item", "anexo", "lei").
3. **Índice BM25 Okapi**, implementado em Python puro (sem biblioteca externa), com os parâmetros clássicos **k1 = 1,5** e **b = 0,75**. O IDF tem **piso de 0,05**, para que um termo presente em quase todas as páginas não fique com peso negativo.
4. **Consulta por pergunta:** o texto da pergunta **mais** os termos-sinal dela ([[Questionário — as 17 perguntas#Os termos de recuperação]]).
5. **Top-k por pergunta:** as `k_rag = 12` páginas de maior pontuação (páginas com pontuação zero não entram).
6. **Arquivos-âncora entram sempre:** toda página de arquivo cujo nome contém "retifica", "suspens", "comunicado", "redesign", "errata" ou "aviso" é incluída, independentemente da pontuação.
7. **União por lote:** as páginas das perguntas do lote são unidas, sem repetição, e ordenadas por precedência documental, arquivo e número.
8. **Contexto:** cada página vai com o marcador `=== ARQUIVO x | PÁGINA n ===`, o mesmo do contexto completo ([[Prompt do extrator]]).

A mesma função escolhe as páginas do lote normal, do reforço do [[Best-of-N]] e do worker em produção — uma só implementação, para não divergir.

> [!danger] A âncora é o que evita a data errada
> O aviso de suspensão de Bertioga/SP tem 1 página e 770 caracteres. Num conjunto de 115 páginas, o BM25 pode não trazê-lo entre as mais pontuadas — e é ele que carrega a data vigente da sessão. Recuperação puramente estatística **não conhece precedência documental**: a regra de negócio precisa entrar no recuperador.

## Por que BM25 e não embeddings

O edital é documento jurídico, de vocabulário fechado e estável: "cessão onerosa", "margem consignável", "valor mínimo", "prova de vida". A pergunta do questionário usa quase as mesmas palavras que a resposta no documento. Nesse regime, a busca léxica é forte; a busca semântica resolveria paráfrase — justamente o que aqui quase não acontece.

| Critério | BM25 | Embeddings + banco vetorial |
|---|---|---|
| Dependência externa | nenhuma | serviço de embeddings e banco vetorial para operar |
| O documento sai do servidor | **não** | sim, a menos de um modelo local |
| Custo por token | zero | por página indexada e por consulta |
| Tempo para indexar | milissegundos | segundos a minutos |
| Explicação do recorte | os termos que casaram | distância num espaço vetorial |

> [!risco] Onde esta escolha pode estar errada, e o gatilho para revê-la
> Se aparecerem editais que descrevem a mesma exigência com palavras muito diferentes ("recadastramento" × "prova de vida" × "recenseamento"), o BM25 perde e o embedding ganharia. A mitigação são os termos-sinal por pergunta, curadoria barata e medida (abaixo). Se a curadoria deixar de escalar, a decisão deve ser reaberta — é um gatilho explícito, não uma porta fechada.

## Por que não fine-tuning

| Motivo | Detalhe |
|---|---|
| Não há volume rotulado | fine-tuning precisa de centenas a milhares de exemplos corretos; os gabaritos humanos são dois |
| O problema é de evidência, não de estilo | ajustar pesos ensina a forma de responder; o que se precisa é que a resposta **exista no documento citado**, e isso é verificação, não treino |
| Manutenção | cada mudança no questionário exigiria retreino |
| Perde rastreabilidade | um modelo ajustado pode "saber" a resposta típica e devolvê-la sem que ela esteja no documento — exatamente a falha que a solução existe para evitar ([[ADR-004 Evidência obrigatória]]) |

Fine-tuning volta à mesa quando houver ao menos 500 editais com gabarito humano conferido **e** o gargalo medido for custo por extração, não acurácia ([[Técnicas avaliadas e descartadas]]).

## O que foi medido

### Contexto completo × RAG no mesmo edital

Pirapó/RS, mesmo modelo (Claude Sonnet 5, esforço `high`), mesmo OCR, mudando só o modo (22/09/2026, com 6 páginas por pergunta):

| Modo | Tokens de entrada | Custo | Acurácia | Críticas | Conflitos achados |
|---|---|---|---|---|---|
| contexto completo | 135.978 | R$ 1,99 | 17/17 | 7/7 | 3 |
| RAG (BM25) | **74.793** | **R$ 1,28** | **17/17** | **7/7** | 2 |

**−45% de entrada, −36% de custo, a mesma acurácia.** O que o RAG perdeu foi **um conflito**: a divergência entre documentos mora justamente nas páginas que o recuperador não trouxe para aquela pergunta. O RAG é bom em **responder** e pior em **cruzar** documentos — por isso o contexto completo continua sendo o modo preferido quando cabe.

### A licitação maior custou menos

| Licitação | Páginas | Modo | Entrada | Custo (Claude Opus 5) |
|---|---|---|---|---|
| Pirapó/RS | 38 | contexto completo | 135.978 | R$ 4,79 |
| Bertioga/SP | **115** | **RAG** | 66.044 | **R$ 2,91** |

Três vezes mais documento, 39% menos custo: não é o tamanho do edital que governa a conta, é a política de recuperação. E a acurácia no RAG se manteve: em Bertioga, o Opus fez 17/17 com 7/7 nas críticas.

### Recall medido

Quando a página com a resposta não entra no contexto, o modelo responde "não localizado" — e ausência declarada é aprovada pela ancoragem, porque não há citação a conferir. **Uma falha de recuperação se disfarça de informação ausente do edital.** Por isso o recall foi medido à parte, a custo zero: para cada resposta **ancorada** (a página citada contém de fato o trecho), a página estava entre as que o BM25 escolheria?

Bertioga/SP, 115 páginas, 66.608 tokens em contexto completo (23/09/2026):

| Páginas por pergunta | Páginas únicas | Tokens | % do documento | Recall |
|---|---|---|---|---|
| 4 | 50 | 28.122 | 42% | 87,8% |
| 6 | 63 | 36.678 | 55% | 95,9% |
| 8 | 73 | 43.721 | 66% | 95,9% |
| **12** (produção) | 87 | 52.493 | 79% | **100%** |
| todas | 115 | 66.608 | 100% | 100% por definição |

> [!important] O trade-off do RAG é mais estreito do que a intuição sugere
> Para chegar a 100% de recall com BM25 é preciso mandar 79% do documento. A economia no ponto seguro é de ~21%, não de ordens de grandeza. E 8 páginas por pergunta é estritamente dominado: custa 10 pontos de contexto a mais que 6 e não recupera nenhuma página nova — quem ajustar o `k` deve ir de 6 para 12, nunca para 8.

### Por que a produção usa 12 páginas por pergunta

A migração `db/026` trocou a semente de `k_rag` de 6 para **12** em 24/09/2026: com 12, o recall foi de 100% em todas as medições; com 6, só chegou a 100% depois da revisão dos termos e numa amostra única. A página que o RAG perde vira "Não localizado" — que, pela política da v3, vai para revisão humana. O custo extra é só de contexto, e só nas extrações em modo RAG. O valor pode ser alterado no [[Página Admin|Admin]]; a migração troca apenas a semente, nunca um valor já editado.

### Termos mortos e o procedimento que os corrige

A medição do recall revelou que dez termos-sinal não apareciam em página nenhuma do corpus e que duas perguntas perdiam páginas por vocabulário ("começar" × "iniciar" na Q10; "convocar a vencedora" × "assinar" na Q7). O procedimento — medir a perda, tirar as palavras do próprio trecho, remedir — fechou cada perda encontrada sem gastar nada; a última, na Q7, levou o recall com 6 páginas de 97,0% para 100% ([[Questionário — as 17 perguntas#Por que os termos foram reescritos a partir dos editais]]). A lista de termos não pode carregar o vocabulário do analista: tem de carregar o vocabulário do edital.

## RAG e cache de prompt

No RAG, cada lote leva páginas diferentes, então o bloco de documentos nunca se repete entre lotes. Marcar esse bloco para cache cobraria a gravação (1,25× o preço de entrada) sem nenhuma leitura — a estimativa era +43% em Bertioga no Claude. Por isso, no RAG, os documentos continuam antes das perguntas, mas sem o 2º ponto de cache ([[Cache de prompt e ordem do prompt]]).

## Limites declarados

- As medições de modo são n=1 por configuração; o recall foi medido em duas licitações com gabarito ou ancoragem conhecida.
- O BM25 não resolve paráfrase; a mitigação é curadoria de termos, e o gatilho de revisão está escrito acima.
- Com recuperação por pergunta, conflitos entre documentos podem ficar fora do contexto de uma pergunta; o contexto completo segue como padrão até 180.000 caracteres por isso.

## Relacionadas

[[MOC IA]] · [[Questionário — as 17 perguntas]] · [[Prompt do extrator]] · [[Cache de prompt e ordem do prompt]] · [[Custo por edital]] · [[Técnicas avaliadas e descartadas]] · [[ADR-010 RAG vs contexto completo]] · [[W23 Extrair]] · [[W22 Ler]] · [[Resultados medidos]]
