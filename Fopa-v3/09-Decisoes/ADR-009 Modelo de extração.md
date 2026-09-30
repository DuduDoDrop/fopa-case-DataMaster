---
tipo: decisao
familia: decisoes
adr: 9
data: 2026-09-22
decisao: aceita
status: verificado
atualizado: 2026-09-28
tags: [decisao, modelo, extracao, custo]
---

# ADR-009 — Modelo de extração

> [!abstract] Em uma frase
> O modelo que responde as 17 perguntas é escolhido por **acurácia e profundidade de leitura**, não por preço — o custo de modelo é pequeno perto do que cada licitação decide —, e a escolha foi **medida** contra gabarito: o extrator é um Claude Opus (hoje o **Opus 5.5**, desde a [[ADR-020 Esforço fixo e Claude Opus 5.5 no extrator]]).

## Problema

O extrator precisa de um modelo de linguagem. As opções diferem em preço (até 5× por token), em contexto (200 mil a 1 milhão de tokens) e em qualidade. A primeira versão desta decisão foi tomada por raciocínio de risco; a pergunta era se a medição a sustentaria.

## Opções (preço de tabela, US$ por milhão de tokens)

| Modelo | Contexto | Entrada / saída |
|---|---|---|
| Claude Opus 5 | 1M | 5 / 25 |
| Claude Sonnet 5 | 1M | 2 / 10 |
| Claude Haiku 4.5 | **200K** | 1 / 5 |

## O que foi medido (22 e 23/09/2026)

**Pirapó/RS, contra gabarito, esforço `high`:**

| Modelo | Acurácia | Críticas | Completude | Custo |
|---|---|---|---|---|
| Opus 5 | 17/17 | **7/7** | **38/41** | R$ 4,79 |
| Sonnet 5 | 17/17 | **7/7** | 26/41 | R$ 2,12 |
| Haiku 4.5 | 15/17 | 6/7 | 19/41 | R$ 0,64 |

- **O Haiku desiste:** respondeu "não localizado" para informação que estava no termo de referência; errou uma crítica; e o teto de 200 mil tokens é real para editais grandes depois do OCR. Descartado como extrator padrão.
- **O Sonnet empata nas críticas por 56% menos** — mas entrega metade da completude e acha menos conflitos entre documentos (2 contra 5 em Pirapó; 16 contra 23 em 7 licitações).
- **Conflito é o que muda o lance:** o Opus foi o único com todos os conflitos nas duas licitações medidas.
- **Nenhum achou a divergência que mais valia** (o objeto da minuta mais estreito que o do edital, 31,9% da folha): virou a regra RN-13 do verificador — a escolha do modelo não substitui regra determinística.
- **Seis modelos de dois fornecedores** depois: no edital difícil (Bertioga, RAG), só os dois Opus ficaram em 17/17 ([[Comparação de modelos]]).

**O custo não é a variável relevante:** num cenário de 400 editais por ano, a diferença entre o modelo mais barato e o mais forte ficava em cerca de US$ 144 por ano — e a economia compraria o risco de não ver um conflito que muda o lance.

## Escolha

- **Extrator:** Claude Opus, com raciocínio adaptativo, saída estruturada e cache de prompt. Era o Opus 5; **passou a ser o Opus 5.5** em 26/09/2026 — mais novo, mais barato por token, empatado em acurácia no edital difícil, com mais completude e mais rápido ([[ADR-020 Esforço fixo e Claude Opus 5.5 no extrator]]).
- **Plano B de fornecedor:** GPT-5.6 Sol ([[ADR-012 Segundo provedor de modelo]]).
- **Verificação:** nenhum modelo ([[ADR-004 Evidência obrigatória]]).
- **O que o desenho original previa e a solução não usa:** modelos diferentes por "agente" (um classificador de escopo com modelo pequeno, um revisor jurídico com modelo médio). Na solução entregue, só o extrator usa modelo generativo: o escopo é regra de vocabulário mais o sinal do Jev ([[ADR-003 Classificação por regras antes de IA]]), e a revisão jurídica é humana ([[Próximos passos]]).

## O que custa

- O modelo mais caro da família — compensado pelo cache de prompt, que derrubou o custo em contexto completo em 32,5% ([[Cache de prompt e ordem do prompt]]).
- Medições n = 1 por configuração: afirma-se a direção e a ordem de grandeza.

## Onde vive em produção

`configuracao.modelo = claude-opus-5-5` e `configuracao.modelo_openai = gpt-5.6-sol`; o catálogo do botão "Extrair com IA" com todos os modelos medidos e o esforço fixo de cada um ([[Modelos e provedores]]).

## O que reabriria a decisão

Um terceiro edital com gabarito em que outro modelo supere o extrator em acurácia **e** conflitos; ou uma política do banco sobre uso de modelo de terceiro em nuvem com documentos externos — se houver restrição, ela manda.

## Relacionadas

[[MOC Decisões]] · [[Modelos e provedores]] · [[Comparação de modelos]] · [[ADR-012 Segundo provedor de modelo]] · [[ADR-020 Esforço fixo e Claude Opus 5.5 no extrator]] · [[Custo por edital]]
