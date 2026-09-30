---
tipo: decisao
familia: decisoes
adr: 20
data: 2026-09-26
decisao: aceita
status: verificado
atualizado: 2026-09-28
tags: [decisao, modelo, esforco, custo, site]
---

# ADR-020 — Esforço fixo e Claude Opus 5.5 no extrator

> [!abstract] Em uma frase
> O esforço de raciocínio deixou de ser escolha de quem clica: é **fixo por modelo** — `medium` em todos os GPT e Claude, nenhum no Haiku 4.5 —, e o extrator Claude passou a ser o **Claude Opus 5.5**, mais barato que o Opus 5 com acurácia equivalente.

## Problema

O botão "Extrair com IA" deixava escolher fornecedor, modelo **e esforço**. O esforço mexe no custo (os níveis `xhigh` e `max` sobem o teto de saída para 32 mil e 64 mil tokens por chamada) sem que quem clica saiba o que ganha com isso.

## Opções

| Opção | Avaliação |
|---|---|
| deixar escolher o esforço | custo imprevisível por clique, sem ganho medido |
| **esforço fixo, no nível de melhor custo-benefício** | o mesmo custo esperado para todo clique no mesmo modelo |

## O que foi medido

- **Varredura de esforço** (Claude Sonnet 5, Pirapó/RS): `high`, `medium` e `low` com a **mesma acurácia (16/17) e as mesmas críticas (7/7)**; o esforço mexe só na saída, cerca de 12% da conta ([[Chain-of-thought e esforço de raciocínio]]).
- **Opus 5.5 × Opus 5:** US$ 4 / 20 contra US$ 5 / 25 por milhão de tokens — ≈ US$ 0,65 contra US$ 0,89 por edital na mesma conta de tokens; empatado em acurácia no edital difícil (17/17), com mais completude (38 contra 37 de 49) e ~30% mais rápido ([[Comparação de modelos]]).

## Escolha

- O catálogo (`api/modelos_ia.py`) guarda o esforço de cada modelo: **`medium`** em GPT-5.6 Sol, GPT-6 Sol, Astra e Luna, Claude Opus 5.5 e Claude Sonnet 5; **nenhum** no Claude Haiku 4.5, que não tem controle de esforço. `medium` é o padrão recomendado pela OpenAI e o do Opus 5.5.
- A tela mostra "Esforço: médio (fixo)" no lugar da escolha; a API recusa (HTTP 422) um esforço diferente do fixo.
- **O extrator Claude é o Claude Opus 5.5** (`configuracao.modelo = claude-opus-5-5`, `effort = medium`); o Opus 5 saiu do catálogo.
- **A extração do agente nunca tem preço de API**, mesmo com o modelo na tabela de preços: aparece como "sem preço de API", nunca como R$ 0,00 nem como estimativa ([[ADR-014 Extração por agente, sem API]]).

> [!info] 28/09/2026: o GPT-6 Luna foi para `high` e voltou para `medium` no mesmo dia
> Em `medium`, pelo botão, o GPT-6 Luna acertou **14 e 13 de 17** em Bertioga/SP contra o gabarito humano, abaixo dos 16 de 17 do Claude Opus 5.5; por ser barato, o esforço dele subiu para `high`. Em `high`, fez **13 de 17** (4 de 7 críticas, completude 26 de 49), com o dobro da saída (cerca de 22 mil tokens contra 10 a 11 mil) e o dobro do tempo (4 min 18 s), por R$ 0,11. Os erros mudam de rodada para rodada, entre 13 e 14 acertos. O esforço do Luna voltou para `medium` no mesmo dia: a medição em produção confirmou esta decisão ([[Comparação de modelos]]).

## O que custa

Uma escolha a menos para quem quisesse experimentar níveis de esforço — o que, pela medição, não mudaria a acurácia.

## O que reabriria a decisão

Um edital em que o esforço maior melhore acurácia ou conflitos de forma mensurável; o preço do Opus 5.5 conferido na fatura divergir da tabela.

## Relacionadas

[[MOC Decisões]] · [[Modelos e provedores]] · [[Chain-of-thought e esforço de raciocínio]] · [[ADR-009 Modelo de extração]] · [[ADR-012 Segundo provedor de modelo]] · [[Página Detalhe da licitação]]
