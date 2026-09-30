---
tipo: tecnica
familia: ia
status: verificado
atualizado: 2026-09-28
fonte_codigo:
  - scripts/fopa/extrator.py
  - scripts/fopa/modelos.py
  - api/extracao.py
  - api/versao.py
tags: [ia, cache, prompt, custo, otimizacao]
---

# Cache de prompt e ordem do prompt

> [!abstract] Em uma frase
> Desde a v3.1 a mensagem começa pelos **documentos** e termina nas **perguntas do lote**; como o cache dos provedores casa por prefixo, o edital passa a ser gravado no cache **uma vez** e lido nas outras chamadas — no Claude em contexto completo, a extração ficou **32,5% mais barata** com a mesma acurácia.

## Papel na solução

O custo desta solução é dominado pela **entrada**: de 76% a 86% do gasto de uma extração é o documento entrando ([[Custo por edital]]). Há duas alavancas na entrada: **quanto** texto se manda ([[RAG com BM25]]) e **quantas vezes** ele é pago. As 17 perguntas saem em 3 chamadas, e em contexto completo o edital inteiro vai nas três. O cache de prompt faz com que as repetições custem uma fração do preço — desde que o prefixo das chamadas seja igual.

## Como o cache é cobrado

| Tipo de token de entrada | Preço relativo à entrada nova | Fonte |
|---|---|---|
| entrada nova | 1,00× | tabela do provedor |
| **gravação** no cache | **1,25×** | Anthropic: documentação de prompt caching; OpenAI: derivado da fatura, igual nos quatro modelos |
| **leitura** do cache | **0,10×** | Anthropic: mesma documentação; OpenAI: tabela oficial (US$ 0,40 de leitura contra US$ 4,00 de entrada) |

A conta de custo da solução aplica esses multiplicadores a cada chamada (`modelos.Uso.usd`). Até 23/09/2026 a gravação era cobrada a 1,00×, o que subestimava em 25% todo custo com cache — corrigido quando a fatura foi conferida linha a linha.

## O defeito que a fatura mostrou

Até a v3.0, a mensagem de cada lote começava pelas perguntas:

```text
LICITAÇÃO: <nome>
Responda as perguntas abaixo…
<BLOCO DE PERGUNTAS>        ← muda a cada lote (Q1–Q6, Q7–Q12, Q13–Q17)
=== DOCUMENTOS ===
<o edital>                  ← idêntico nos três lotes
=== FIM DOS DOCUMENTOS ===
```

Com o bloco que muda **antes** do bloco que se repete, o prefixo divergia logo no começo, e o documento era **regravado** a cada lote em vez de lido. Medido na fatura de 23/09/2026:

- **OpenAI (`gpt-5.6-sol`):** 45,6% do custo foi **gravação de cache** — 122.407 tokens gravados contra 54.376 lidos, e gravar custa mais que a entrada nova (US$ 5,00 contra US$ 4,00 por milhão).
- **Claude (`claude-opus-5`):** as duas linhas de cache somaram US$ 0,10 contra US$ 10,87 de entrada sem cache. O `cache_control` marcava só a instrução de sistema (~2,8 mil tokens), e o edital (80 mil tokens de mediana) ia fora do cache. Em 11 extrações, 1.364.801 tokens de entrada e só 30.840 lidos do cache — 2,3%.

A economia estimada invertendo a ordem era de ~28% do custo total.

## A ordem da v3.1

```text
system  ← instrução fixa .................................. cache_control (1º ponto de cache)
user    ← LICITAÇÃO + === DOCUMENTOS === … === FIM ===        igual em todos os lotes
          ............................................... cache_control (2º ponto, só contexto completo)
          perguntas do lote + instrução final                muda a cada lote
```

- **O prefixo** (licitação + documentos até `=== FIM DOS DOCUMENTOS ===`) é igual em todos os lotes que leem as mesmas páginas. O **sufixo** traz as perguntas e a instrução final.
- **Claude:** o prefixo vira um bloco de texto com `cache_control` — o **2º ponto de cache** (o 1º continua sendo o sistema). O 1º lote grava o documento; os seguintes, e as chamadas de reforço do [[Best-of-N]], o leem.
- **OpenAI:** o cache é automático por prefixo; a mensagem vai como texto único começando pelos documentos.
- **RAG:** cada lote recupera páginas diferentes, o prefixo nunca se repete e marcá-lo cobraria a gravação sem leitura (+43% estimado em Bertioga no Claude). No RAG os documentos continuam antes das perguntas, num texto único, **sem** o 2º ponto de cache.
- **A ordem antiga continua no código, byte a byte** (`perguntas-primeiro`), só para medir o "antes" com o mesmo código. O padrão de produção é `documentos-primeiro`.

## O resultado medido

Medição de 28/09/2026 (`scripts/35_antes_depois.py`, esforço `high`). "Antes" é a ordem antiga com uma tentativa; "depois" é a v3.1 (nova ordem e [[Best-of-N]]).

### Claude — o documento passou a ser lido do cache

Pirapó/RS, contexto completo, Claude Opus 5.5:

| | Chamadas | Entrada nova | Cache gravado | Cache lido | Custo |
|---|---|---|---|---|---|
| antes | 3 | 135.984 | 1.542 | 3.084 | R$ 3,71 |
| depois | 5 | 2.221 | 44.743 | 186.682 | **R$ 2,50** |

O documento é gravado uma vez e lido nas outras quatro chamadas — inclusive nas duas do reforço, que por isso saem quase de graça. Duas chamadas a mais, e a conta caiu **32,5%**, com a mesma acurácia (16/17) e as mesmas críticas (7/7). A estimativa de ~28% se confirmou com folga.

### OpenAI — o cache quase nunca é lido, em nenhuma das duas ordens

| | Chamadas | Entrada nova | Cache gravado | Cache lido |
|---|---|---|---|---|
| Pirapó antes | 3 | 9 | 81.484 | 0 |
| Pirapó depois | 5 | 15 | 108.497 | 27.016 |
| Bertioga antes | 3 | 9 | 40.848 | 0 |
| Bertioga depois | 5 | 15 | 51.597 | 0 |

A OpenAI registra quase toda a entrada como **gravação** de cache e leu uma única vez em 16 chamadas — nem a instrução de sistema, idêntica em todas as chamadas e acima do mínimo de 1.024 tokens, foi lida. Com o prefixo igual e as chamadas em sequência, o que falta não é a ordem: é a requisição cair onde o cache está. Resultado: em Pirapó, com o reforço, o GPT ficou **21,6% mais caro**.

**Em produção, a mesma diferença (28/09/2026).** Na extração de Itapecuru Mirim/MA pelo botão, o Claude Haiku 4.5 gravou o edital uma vez (66.110 tokens) e o leu nas outras quatro chamadas (264.440 tokens); o GPT-6 Luna gravou nas cinco (253.693 tokens) e não leu nenhuma ([[Best-of-N]]).

**E o esforço parece entrar na chave do cache (28/09/2026).** Em Bertioga/SP, a extração 2710 do GPT-6 Luna leu o cache inteiro da 2709, com o mesmo prompt e o mesmo esforço, e custou R$ 0,03; a 2711, com o mesmo texto e esforço `high`, não leu nada nos lotes ([[Comparação de modelos]]).

> [!danger] O defeito continua aberto na OpenAI
> A próxima hipótese é o `prompt_cache_key` — a chave com que a OpenAI roteia o cache —, igual em todos os lotes da mesma licitação. Ela não foi medida ([[Próximos passos]]). Enquanto isso, o provedor padrão da extração é o Claude, e o GPT é o plano B ([[Modelos e provedores]]).

### Resumo por cenário

| Cenário | Efeito da v3.1 no custo |
|---|---|
| Claude, contexto completo (Pirapó) | **−32,5%** |
| Claude, RAG (Bertioga) | +7,2% — sem prefixo comum não há leitura; o reforço é custo puro |
| GPT, contexto completo (Pirapó) | +21,6% |
| GPT, RAG (Bertioga) | −4,6% |

## Efeitos colaterais que foram tratados

- **A `versao_prompt` mudou**, porque a mensagem montada mudou: as execuções de antes e de depois da v3.1 se distinguem no banco. A `versao_regras` ficou igual — verificador, questionário e políticas não mudaram —, por isso a v3.1 não obrigou a reverificar o acervo ([[Prompt do extrator#Versão do prompt]]).
- **As chamadas antigas continuam legíveis.** O banco guarda chamadas nas duas ordens, e a reverificação e o replay voltam a elas; a leitura dos ids das perguntas procura o bloco de perguntas depois do fim dos documentos (ordem nova) ou antes deles (ordem antiga). Uma linha "Q3. …" dentro de um edital não conta como pergunta.
- **O provedor simulado para no fim do bloco de documentos**: na ordem nova as perguntas vêm depois, e sem isso ele as leria como texto da última página. Um teste confere que ele dá as mesmas respostas nas duas ordens.
- **Limite de taxa:** segundo a documentação da Anthropic, tokens lidos do cache não contam para o limite de tokens de entrada por minuto; o cache compra teto de taxa além de dinheiro ([[Escalabilidade]]).

## Relacionadas

[[MOC IA]] · [[Prompt do extrator]] · [[RAG com BM25]] · [[Best-of-N]] · [[Custo por edital]] · [[Modelos e provedores]] · [[Antes e depois da v3.1]] · [[ADR-024 Best-of-N e documentos antes das perguntas]] · [[W23 Extrair]]
