---
tipo: tecnica
familia: ia
status: verificado
atualizado: 2026-09-28
fonte_codigo:
  - api/extracao.py
  - api/modelos_ia.py
  - scripts/fopa/modelos.py
tags: [ia, chain-of-thought, raciocinio, effort, test-time-compute, custo]
---

# Chain-of-thought e esforço de raciocínio

> [!abstract] Em uma frase
> O extrator **raciocina antes de responder** — raciocínio adaptativo no Claude, `reasoning.effort` na OpenAI —, porque a tarefa exige comparar documentos que se contradizem; o nível de esforço é **fixo em `medium`** desde 26/09/2026, porque a medição mostrou a mesma acurácia em `low`, `medium` e `high` e o raciocínio é a maior parte da saída paga; o GPT-6 Luna chegou a ir para `high` em 28/09/2026 e voltou no mesmo dia pelo mesmo motivo ([[ADR-020 Esforço fixo e Claude Opus 5.5 no extrator]]).

## Papel na solução

*Chain-of-thought* (cadeia de raciocínio) é o modelo produzir passos intermediários antes da resposta final. Nos modelos atuais isso não é mais um truque de prompt ("pense passo a passo"): é um **canal de raciocínio** do próprio modelo, ligado por parâmetro e cobrado como saída. Controlar quanto o modelo raciocina é uma forma de *test-time compute scaling* — gastar mais computação na inferência para responder melhor.

Aqui o raciocínio tem um motivo concreto: um edital de folha tem vários documentos, e eles se contradizem. Sem raciocínio, o modelo tende a pegar a **primeira ocorrência** — em Bertioga/SP seria a data de sessão do edital, que um comunicado posterior suspendeu. Com raciocínio, ele compara, aplica a precedência documental e descreve o conflito ([[Prompt do extrator#As nove regras absolutas]]).

## Como está configurado em produção

| Provedor | Parâmetro de raciocínio | Nível |
|---|---|---|
| Claude (Opus 5.5, Sonnet 5) | `thinking: {type: "adaptive"}` + `output_config.effort` | `medium` |
| OpenAI (GPT-5.6 Sol, GPT-6 Sol, Astra e Luna) | `reasoning.effort` | `medium` |
| Claude Haiku 4.5 | não aceita raciocínio adaptativo nem esforço | — (o corpo vai só com a saída estruturada) |

- **Adaptativo:** o modelo decide quanto raciocinar em cada chamada, dentro do nível de esforço. O parâmetro antigo de orçamento fixo de tokens de raciocínio (`budget_tokens`) foi removido nos modelos atuais e devolve erro — a profundidade se controla por esforço.
- **Teto de saída por chamada:** 16.000 tokens no esforço padrão (32.000 em `xhigh` e 64.000 em `max`, níveis que o catálogo não usa). O raciocínio conta dentro desse teto.
- **O raciocínio não é guardado nem mostrado.** A leitura da resposta usa só os blocos de texto — nunca o bloco de raciocínio — e o esquema de saída não tem campo para "justificativa". O que fica é a **evidência** (arquivo, página e trecho literal), que o [[Verificador determinístico]] confere. O raciocínio ajuda o modelo a achar a evidência; quem prova a resposta é a evidência.

## O esforço é fixo por modelo

O catálogo do botão "Extrair com IA" (`api/modelos_ia.py`) lista, para cada provedor, os modelos disponíveis, **cada um com o esforço já definido**. A tela mostra "Esforço: médio (fixo)" no lugar de uma escolha, e a API recusa (HTTP 422) qualquer esforço diferente do fixo ([[ADR-020 Esforço fixo e Claude Opus 5.5 no extrator]], [[Página Detalhe da licitação]]).

Por que fixar: o esforço mexe no custo (os níveis `xhigh` e `max` sobem o teto de saída para 32 mil e 64 mil tokens) sem que quem clica saiba o que ganha com isso. Uma escolha a menos no botão, e o mesmo custo esperado para todo clique no mesmo modelo.

Por que `medium`: a varredura abaixo deu a mesma acurácia e as mesmas críticas nos três níveis; `medium` é o padrão recomendado pela OpenAI para a maioria dos casos e o padrão do Claude Opus 5.5.

## O que foi medido

### Varredura de esforço — o esforço não é alavanca de acurácia

Pirapó/RS, Claude Sonnet 5, contexto completo, mesmo edital e mesmo prompt (22/09/2026):

| Esforço | Tokens de entrada | Tokens de saída | Custo | Acurácia | Críticas |
|---|---|---|---|---|---|
| high | 135.978 | 8.781 | R$ 1,85 | 16/17 | 7/7 |
| medium | 135.978 | 4.688 | R$ 1,65 | 16/17 | 7/7 |
| low | 135.978 | 4.259 | R$ 1,62 | 16/17 | 7/7 |

**Em produção, a mesma conclusão (28/09/2026):** em Bertioga/SP, pelo botão, o GPT-6 Luna em `high` acertou 13 de 17 contra o gabarito, o mesmo patamar do `medium` (14 e 13), gerando o dobro da saída e levando o dobro do tempo ([[Comparação de modelos]]).

- A **entrada é idêntica** nos três níveis: o esforço só muda a saída.
- Cortar o raciocínio pela metade cortou cerca de **11–12% da conta**, sem mudar acurácia nem críticas.
- A alavanca de custo real está na entrada — quanto texto se manda e quantas vezes ([[RAG com BM25]], [[Cache de prompt e ordem do prompt]]).

### O raciocínio é a maior parte da saída — e é invisível

GPT-5.6 Sol, 23/09/2026:

| Licitação | Tokens de saída | Dos quais raciocínio |
|---|---|---|
| Pirapó/RS (contexto completo) | 13.106 | **9.851 (75%)** |
| Bertioga/SP (RAG) | 16.495 | **13.003 (79%)** |

> [!risco] Três de cada quatro tokens de saída não aparecem na resposta
> O raciocínio é cobrado como saída e não aparece no texto. Um orçamento feito pelo tamanho da resposta subestimaria o custo em cerca de 4 vezes. Por isso o custo de cada chamada é calculado sobre os **tokens de saída informados pelo provedor**, que já incluem o raciocínio, e nunca sobre o tamanho do JSON devolvido; nas medições, o harness separa os tokens de raciocínio (subconjunto da saída, nunca parcela somada) para tornar essa parcela visível.

## Onde a solução não usa raciocínio de modelo

| Etapa | Por quê |
|---|---|
| Verificação | determinística por princípio — um verificador que raciocinasse com IA herdaria o modo de falha que deve detectar ([[Verificador determinístico]]) |
| Escopo (é folha?) | regra de vocabulário antes de IA, a custo zero ([[Regras antes de IA]]) |
| Jev | é um classificador de decisão tipada; não raciocina nem tem esforço — o que faz o papel de "esforço" nele é quanto texto vai no estado ([[Jev — score de escopo e sustentação]]) |

## Dois eixos da mesma ideia

A solução gasta mais computação na inferência de duas formas, e as duas foram medidas:

| Eixo | Como | Quando |
|---|---|---|
| **Profundidade** (este) | mais raciocínio por chamada | sempre, no nível fixo `medium` |
| **Amostragem** ([[Best-of-N]]) | mais tentativas, escolhidas pelo verificador | só nas respostas que falharam |

A medição mostrou que subir a profundidade não muda a acurácia neste domínio, enquanto a amostragem dirigida recuperou uma pergunta crítica sem piorar nenhuma — por isso o gasto extra foi colocado no segundo eixo.

## Relacionadas

[[MOC IA]] · [[Modelos e provedores]] · [[Prompt do extrator]] · [[Best-of-N]] · [[Custo por edital]] · [[Técnicas avaliadas e descartadas]] · [[ADR-020 Esforço fixo e Claude Opus 5.5 no extrator]] · [[W23 Extrair]]
