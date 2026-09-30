---
tipo: avaliacao
familia: avaliacao
status: verificado
atualizado: 2026-09-28
fonte_codigo:
  - scripts/11_avaliar.py
tags: [avaliacao, variancia, metodo]
---

# Variância e como citar números

> [!abstract] Em uma frase
> Três execuções idênticas do mesmo modelo no mesmo edital mostraram que **o que é verificável é estável** (ancoragem e críticas com desvio zero; custo e tempo com 1%) e **o que é descoberta varia** (conflitos com 19% de amplitude) — e isso define como cada número desta documentação pode ser afirmado.

## Papel na solução

A saída de um modelo de linguagem varia entre execuções; a do verificador, não. Sem medir a variância, qualquer número de uma execução só seria apresentado com precisão indevida. Esta nota é a régua de como os números das outras notas devem ser lidos e repetidos.

## A medição — n = 3 na mesma configuração

Claude Opus 5 sobre Bertioga/SP (115 páginas, RAG), mesmo edital, mesmo modo, mesmo prompt:

| Métrica | As três execuções | Desvio | Amplitude |
|---|---|---|---|
| **Ancoragem** | 16, 16, 16 | **0,00** | **0%** |
| **Críticas corretas** | 7/7, 7/7, 7/7 | **0,00** | **0%** |
| Acurácia | 16/17, 17/17, 17/17 | — | 1 resposta |
| Custo | R$ 3,086 · 3,041 · 3,056 | 0,02 | **1%** |
| Tempo | 107,2 · 106,9 · 108,3 s | 0,60 | **1%** |
| Tokens de saída | 10.360 · 10.280 · 10.401 | 50 | 1% |
| **Conflitos achados** | 5, 5, **6** | 0,47 | **19%** |

A separação faz sentido: **ancoragem** é a conferência determinística de uma citação — desvio zero, três vezes. **Conflito** exige que o modelo *perceba* que dois documentos discordam, e perceber varia. Custo e tempo são previsíveis em 1%, o que torna o orçamento defensável sem margem de segurança inventada.

Outra observação independente: o Claude Sonnet 5 em Pirapó, mesma configuração, medido duas vezes, deu 17/17 e 16/17 de acurácia e R$ 2,12 e R$ 1,85 de custo — com a ancoragem estável (14/15 nas duas).

## Como cada número deve ser citado

| Número | Como afirmar |
|---|---|
| Ancoragem, críticas corretas | **valor exato** — não oscilou |
| Custo por edital, latência | **valor exato, ±1%** |
| Acurácia | o valor, com a ressalva de **±1 resposta em 17** |
| **Conflitos detectados** | **faixa**, nunca número fechado: em Bertioga, 5 a 6 |
| Comparação entre modelos | **ordem de grandeza e direção**, nunca a terceira casa — a maior parte das medições é n = 1 por configuração |

Dizer "o sistema encontra 5 conflitos" seria falso com precisão indevida. Dizer "encontra de 5 a 6, e o Sonnet encontrou 5 no mesmo edital" é o que os dados sustentam.

## Médias sobre conjuntos diferentes não se comparam

No benchmark consolidado, um modelo rodou em 2 licitações e os outros em 7. Sem recorte, a taxa de "não localizado" dele **parecia melhor** — quando na verdade ele só tinha visto os dois editais em que todos foram bem. Por isso o consolidador emite o **recorte comparável**: só as licitações em que todas as configurações rodaram ([[Comparação de modelos]]).

## O que n = 3 ainda não resolve

- Três execuções numa licitação. A variância **entre licitações** é desconhecida e provavelmente maior: Bertioga tem 9 arquivos com suspensão e esclarecimentos; Pirapó tem 3 sem nenhuma retificação. O desvio de conflitos medido aqui é um piso, não um teto.
- As medições de modelo, modo, esforço e da v3.1 são, em sua maioria, n = 1 por configuração.
- O corpus do PNCP é uma **janela móvel**, não um censo: duas coletas do mesmo termo com horas de diferença devolvem conjuntos diferentes. Números de corpus devem ser citados com a data da coleta ("snapshot de 23/09/2026"), porque quem refizer obterá outro número.

## Relacionadas

[[MOC Avaliação]] · [[Métricas]] · [[Resultados medidos]] · [[Comparação de modelos]] · [[Harness de avaliação]] · [[Disponibilidade do PNCP]]
