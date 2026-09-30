---
tipo: decisao
familia: decisoes
adr: 24
data: 2026-09-28
decisao: aceita
status: verificado
atualizado: 2026-09-28
tags: [decisao, extracao, cache, best-of-n, custo]
---

# ADR-024 — Best-of-N e documentos antes das perguntas

> [!abstract] Em uma frase
> A v3.1 fez duas mudanças no extrator, medidas antes de irem para produção: a mensagem passou a começar pelos **documentos** e terminar nas **perguntas**, para o edital ser lido do cache nas chamadas seguintes (−32,5% no Claude em contexto completo), e as respostas que falham ganham **até duas tentativas extras**, escolhidas pelo **verificador determinístico** (Best-of-N com N = 3).

## Problema

- **A ordem do prompt desperdiçava o cache.** O cache dos provedores casa por prefixo; com as perguntas do lote antes dos documentos, o edital era **regravado** a cada lote. A fatura mostrou o defeito: 45,6% do custo da OpenAI era gravação de cache; no Claude, o cache cobria 2,3% da entrada. A correção era barata, mas invalidava as medições de comparação — por isso esperou uma remedição planejada.
- **Uma resposta que falha fica falhada.** Best-of-N era a técnica que o estudo de técnicas mandara construir: o scorer já existia e não é um modelo.

## Opções

| Opção | Avaliação |
|---|---|
| manter a ordem antiga | é a maior economia disponível no projeto |
| um modelo como juiz dos candidatos | herdaria a subjetividade do juiz |
| reamostrar as 17 perguntas | N vezes o custo para mexer no que já ancora |
| **documentos primeiro + Best-of-N só no que falha, escolhido pelo verificador** | adotado |

## Escolha

**Documentos primeiro** ([[Cache de prompt e ordem do prompt]]):
- a mensagem em duas partes — licitação + documentos (igual nos lotes) e perguntas do lote + instrução final;
- no Claude, o bloco de documentos é o **2º ponto de cache** (o 1º é o sistema) — **só em contexto completo**; no RAG cada lote tem outras páginas e o bloco não é marcado;
- na OpenAI, o cache por prefixo é automático;
- a ordem antiga continua no código, byte a byte, só para medir o "antes".

**Best-of-N** ([[Best-of-N]]):
- reamostra só o que **falhou** (reprovada, ou "não localizado" numa pergunta que se aplica), no máximo N − 1 = 2 rodadas, com o mesmo contexto;
- o verificador escolhe (ancorada > página corrigida > ausência > reprovada; similaridade desempata; empate fica o original); um original que ancora nunca é trocado;
- o n8n chama o modelo; o worker decide (`POST /reforco`); cada chamada extra é gravada com a rodada (`db/050`); o registro vai para `verificacoes.melhor_de_n`;
- uma chamada de reforço que falha não gera candidato e não derruba a extração; com o gasto do dia no teto, não há reforço.

## O que foi medido (28/09/2026, R$ 23,79)

| Edital · modelo | Δ custo | Acurácia | Críticas |
|---|---|---|---|
| Pirapó · Claude Opus 5.5 (contexto completo) | **−32,5%** | 16/17 → 16/17 | 7/7 → 7/7 |
| Pirapó · GPT-5.6 Sol | +21,6% | 17/17 → 16/17 | 7/7 → 6/7 |
| Bertioga · Claude (RAG) | +7,2% | 16/17 → 16/17 | 6/7 → 6/7 |
| Bertioga · GPT (RAG) | −4,6% | 14/17 → 15/17 | 4/7 → 5/7 |

Reforço: 8 respostas reforçadas — 4 ausências confirmadas, 3 erros sistemáticos, **1 crítica recuperada** (a Q1 de Bertioga no GPT), **nenhuma piorada** ([[Antes e depois da v3.1]]).

## O que custa

- A `versao_prompt` mudou (as execuções de antes e de depois se distinguem); a `versao_regras` não — sem reverificação do acervo.
- O reforço entra no custo da execução e no gasto do dia; a reserva da vaga (R$ 6,56) não o inclui — com várias extrações em curso, rodadas já iniciadas podem passar um pouco do teto.
- Na OpenAI, o cache continua quase sem leitura: a próxima hipótese é o `prompt_cache_key`, não medida.

## Onde vive em produção

`extrator.montar_partes` e `modelos.conteudo_claude` (a ordem); `melhor_de_n.py` e o `POST /reforco` (o reforço); o laço do [[W23 Extrair]]; a escolha no `POST /verificar` do [[W24 Verificar e publicar]]; `configuracao.melhor_de_n = 3`; a nota "escolhida a 2ª de 3 tentativas" no detalhe.

> [!success] Em produção, pelo botão do site (28/09/2026)
> Itapecuru Mirim/MA, a mesma licitação em dois modelos baratos: no **GPT-6 Luna (R$ 0,20)**, o reforço ancorou a Q11 na 3ª tentativa e a Q12 na 2ª — de 2 reprovadas para **0**, com 16 de 16 respostas ancoradas e R$ 0,08 nas duas rodadas; no **Claude Haiku 4.5 (R$ 0,78)**, as mesmas perguntas não ancoraram em nenhuma tentativa. O cache da ordem nova funcionou no Haiku (o edital gravado uma vez, lido quatro) e não no Luna (gravado cinco vezes, lido nenhuma). Sem gabarito: ancoragem, não acurácia ([[Best-of-N]]).

## O que reabriria a decisão

A medição do `prompt_cache_key` na OpenAI; um edital em que o reforço piore resultado (impossível por construção, mas monitorado pelo registro).

## Relacionadas

[[MOC Decisões]] · [[Best-of-N]] · [[Cache de prompt e ordem do prompt]] · [[Antes e depois da v3.1]] · [[W23 Extrair]] · [[W24 Verificar e publicar]] · [[Técnicas avaliadas e descartadas]]
