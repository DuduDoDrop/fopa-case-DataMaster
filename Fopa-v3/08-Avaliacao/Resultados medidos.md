---
tipo: avaliacao
familia: avaliacao
status: verificado
atualizado: 2026-09-28
testado_em: 2026-09-28
tags: [avaliacao, resultados, nucleo]
---

# Resultados medidos

> [!abstract] Em uma frase
> Tudo o que foi medido sobre a solução, por tema e com data — da primeira extração de referência à operação em produção em 28/09/2026 —; nada aqui é projeção, e cada linha aponta para a nota com o detalhe e o método.

## Papel na solução

É o índice das evidências. Uma decisão da família [[MOC Decisões]] ou uma afirmação da [[Visão geral da solução]] deve poder ser rastreada até uma linha desta nota. Como cada número deve ser citado (exato, ±1%, faixa) está em [[Variância e como citar números]].

## Em produção — 28/09/2026

Lido no site, só por navegação.

| Recorte | Números |
|---|---|
| **Licitações ativas** ([[Página Painel]]) | **71** licitações de folha em andamento — 20 fecham em até 7 dias, 25 entre 8 e 20 dias, 16 depois de 20 dias, 10 sem data de sessão; **59 extraídas**; ancoragem **98,67%** (822 de 833 respostas); 172 respostas para revisar; custo das extrações R$ 37,02 (49 extraídas fora da API); não reconhecidas como folha pela IA: 0 de 76 (nota média 92%) |
| **Histórico** ([[Página Histórico]]) | **2.020** licitações — 751 com vencedor homologado, 60 revogadas ou anuladas, 1.209 sem vencedor registrado; 1.433 anteriores a 2026; **2.019 extraídas**, 13 sem documento na fonte; ancoragem **99,96%** (25.114 de 25.122); 5.473 respostas para revisar; custo R$ 15,54 (2.011 extraídas fora da API) |
| **Mercado** ([[Página Analytics de Mercado]]) | 2.071 licitações no histórico do PNCP; **726 compradas**; **R$ 5,56 bilhões** homologados; 79 instituições compradoras; 284 desertas ou fracassadas; maiores compradoras por quantidade: Caixa (224), Bradesco (195), Santander (68), Itaú (48), Banco do Brasil (35), Banrisul (15) |
| **Republicações** ([[Página Analytics Histórico FOPA]]) | 437 licitações publicadas de novo; 201 ainda sem comprador; 236 compradas depois de republicar |
| **Revisão** ([[Página Revisão]]) | 5.690 revisões abertas em 2.009 licitações; aba Escopo com 1 candidata pendente e 281 licitações rotuladas |
| **Gasto com IA** (fatura, desde 21/09) | US$ 47,82 ≈ R$ 243,89 — Claude US$ 24,06, Jev US$ 17,85, GPT US$ 5,91 |
| **Caso ponta a ponta** | Itapecuru Mirim/MA: descoberta às 06:00, aviso às 06:04, baixada e lida às 06:20 em 36,7 s, extraída a pedido às 10:22 (Claude Haiku 4.5, 5 chamadas, R$ 0,78), publicada às 10:24, e-mail às 10:25 ([[W20 Processar uma licitação]]); depois, a mesma licitação extraída de novo pelo botão com GPT-6 Luna: R$ 0,20 e 16 de 16 respostas ancoradas ([[Best-of-N]]) |

## Extração e verificação

| Resultado | Detalhe |
|---|---|
| Execução de referência — Bertioga/SP, 9 arquivos, 115 páginas, RAG, Claude Opus 5 (22/09) | 17/17 ancoradas, 13 aprovadas, 4 em revisão por conflito declarado, 0 reprovadas; 66.044 tokens de entrada, 9.804 de saída; 106 s de modelo; R$ 2,98 |
| O que o sistema achou sozinho em Bertioga | a **suspensão** da sessão (a data vigente não estava no edital); **três rótulos** para o mesmo valor; a **pirâmide truncada** (faltam 488 vínculos, nas faixas mais altas); a **unidade** da Q14 (vínculos, não pessoas); e a **garantia** que a leitura humana registrou como exigência e era só pedido de licitante ([[Gabaritos]]) |
| O modelo supera o regex? | regex 0/13 ancoradas contra 17/17 do modelo ([[Comparação de modelos]]) |
| Guarda numérica na ancoragem | citações com um algarismo trocado passavam com similaridade 0,98; com a guarda, zero regressão em 190 respostas reais de dois fornecedores ([[Verificador determinístico]]) |
| Correções de regra remedidas a custo zero | Haiku em Pirapó de 0/13 para 12/13 ancoradas; RN-09 silenciosa na pirâmide íntegra e com 488 faltantes na truncada, nos três modelos ([[A medição que mediu o medidor]]) |

## Modelos

| Resultado | Detalhe |
|---|---|
| A ancoragem não separa modelos; a profundidade separa | ancoragem de 92% a 100% em todos; conflitos 10 / 7 / 4 e completude caindo pela metade do topo à base ([[Comparação de modelos]]) |
| Dois gabaritos, seis modelos | os dois Claude Opus em 17/17 no edital difícil; GPT de 11/17 a 15/17 ali (o GPT-6 Luna recontado com o avaliador corrigido); completude Claude 33–38 contra GPT 17–26 |
| Plano B (GPT-5.6 Sol) | ancoragem 100% nos dois gabaritos; acurácia 16/17 e 15/17 ([[Modelos e provedores]]) |

## Recuperação, esforço e custo

| Resultado | Detalhe |
|---|---|
| RAG × contexto completo no mesmo edital | −45% de entrada, −36% de custo, a mesma acurácia (17/17, 7/7); um conflito a menos ([[RAG com BM25]]) |
| A licitação maior custou menos | Bertioga (115 páginas, RAG) R$ 2,91 contra Pirapó (38 páginas, contexto completo) R$ 4,79 |
| Recall da recuperação | 100% com 12 páginas por pergunta em Bertioga; termos mortos corrigidos levaram Pirapó de 93% para 100% |
| Esforço de raciocínio | `high`, `medium` e `low` com a mesma acurácia e críticas; o esforço mexe só na saída (~11% da conta) ([[Chain-of-thought e esforço de raciocínio]]) |
| Raciocínio na saída | 75% a 79% dos tokens de saída do GPT-5.6 Sol |
| A entrada domina o custo | 76% a 86% do gasto de uma extração ([[Custo por edital]]) |
| Fatura conferida linha a linha | preço da OpenAI derivado da fatura bate com a tabela dentro de 0,01%; a fatura da Anthropic vinha em centavos com a moeda "USD" — pego porque o custo é ancorado em tokens × preço |
| O defeito de cache | 45,6% do custo da OpenAI era gravação de cache; no Claude, o cache cobria 2,3% da entrada ([[Cache de prompt e ordem do prompt]]) |

## v3.1 — 28/09/2026

| Resultado | Detalhe |
|---|---|
| Documentos antes das perguntas | Claude em contexto completo **−32,5%**, mesma acurácia; RAG +7,2%; GPT +21,6% em Pirapó ([[Antes e depois da v3.1]]) |
| Best-of-N | 8 respostas reforçadas: 4 ausências confirmadas, 3 erros sistemáticos, **1 crítica recuperada**, nenhuma piorada ([[Best-of-N]]) |
| Best-of-N em produção | Itapecuru Mirim/MA, pelo botão: no GPT-6 Luna, o reforço ancorou a Q11 na 3ª tentativa e a Q12 na 2ª — de **2 reprovadas para 0**, 16 de 16 ancoradas, R$ 0,20 no total e R$ 0,08 nas duas rodadas; no Claude Haiku 4.5 (R$ 0,78), as mesmas perguntas não ancoraram em nenhuma tentativa. Sem gabarito: ancoragem, não acurácia; n = 1 por modelo ([[Best-of-N]]) |
| Cache em produção | Claude Haiku 4.5: o edital gravado uma vez (66.110 tokens) e lido nas outras quatro chamadas (264.440); GPT-6 Luna: gravado nas cinco (253.693) e lido em nenhuma ([[Cache de prompt e ordem do prompt]]) |
| GPT-6 Luna no gabarito, pelo botão | Bertioga/SP, v3.1: **14 e 13 de 17** em `medium` e **13 de 17** em `high` (o dobro de saída e de tempo, R$ 0,11), contra 16 de 17 do Claude Opus 5.5; o `high` foi testado e desfeito no mesmo dia ([[Comparação de modelos]], [[ADR-020 Esforço fixo e Claude Opus 5.5 no extrator]]) |
| Estimativa × gasto real da medição | R$ 24,22 estimados sem chamar modelo; R$ 23,79 gastos |

## Variância

| Resultado | Detalhe |
|---|---|
| n = 3, Claude Opus 5, Bertioga | ancoragem e críticas com desvio **zero**; custo e tempo com 1%; conflitos com **19%** de amplitude (5, 5, 6) ([[Variância e como citar números]]) |

## Leitura e documentos

| Resultado | Detalhe |
|---|---|
| Quanto OCR o acervo exige | 12,7% dos arquivos e 8,6% das páginas, em 324 PDFs de 108 licitações; uma licitação em sete tem ao menos um arquivo escaneado ([[OCR]]) |
| Perfis de OCR | texto: 150 dpi, 92,97% de similaridade de palavra; tabela: 400 dpi, zero valores errados |
| Conversão de formatos | 40 das 41 licitações de folha presas por formato destravadas ([[Conversão de formatos]]) |

## Escopo e Jev

| Resultado | Detalhe |
|---|---|
| O score do filtro no acervo (1.162 licitações) | discordâncias convictas regra × Jev de 75 para 2; probabilidade média de acerto do filtro de 0,83 para 0,91 ([[Regras antes de IA]]) |
| Camada de ajuste do escopo | 85 licitações tiradas, 0 folhas publicadas perdidas; 27 de 28 rótulos humanos "fora" e 53 de 57 casos do Jev pegos |
| Critério v3.1 do Jev | folhas reconhecidas de 96,8% para 100%; AUC de 0,969 para 0,982 ([[Jev — score de escopo e sustentação]]) |
| "Sustenta?" adversarial | data trocada → "contradiz" 1,00; valor inventado → "nada diz" 1,00; custo ~US$ 0,01 por licitação |

## Tempo para agir

| Resultado | Detalhe |
|---|---|
| Antecedência entre o registro no PNCP e o fim do prazo de propostas (198 licitações, 23/09/2026) | mínimo 0, p25 12, **mediana 16**, p75 18 dias úteis; **94,4%** com ao menos 10 dias úteis; 97,5% com ao menos 5 ([[Problema de negócio]]) |
| O que isso significa | o registro no PNCP pode chegar depois da divulgação no diário oficial — o tempo que conta é o que sobra depois que a licitação aparece no portal, e a descoberta roda às 06:00 de todo dia útil ([[W01 Descoberta]]) |

## Relacionadas

[[MOC Avaliação]] · [[Métricas]] · [[Comparação de modelos]] · [[Antes e depois da v3.1]] · [[Variância e como citar números]] · [[Harness de avaliação]] · [[Gabaritos]] · [[Visão geral da solução]]
