---
tipo: referencia
familia: avaliacao
status: verificado
atualizado: 2026-09-28
fonte_codigo:
  - scripts/fopa/verificador.py
  - scripts/15_acuracia.py
  - scripts/46_recall_recuperacao.py
  - scripts/49_antecedencia.py
  - api/consultas.py
tags: [avaliacao, metricas, nucleo]
---

# Métricas

> [!abstract] Em uma frase
> A solução é medida por um conjunto de métricas que respondem perguntas diferentes — **a citação existe?** (ancoragem), **a resposta está certa?** (acurácia e críticas), **diz tudo o que importa?** (completude), **percebeu as contradições?** (conflitos), **quanto sobra para a pessoa?** (revisão), **quanto custa?** e **quanto tempo sobra para agir?** —, cada uma com o que ela **não** prova escrito ao lado.

## Papel na solução

Uma métrica só é útil se se sabe o que ela não mede. A confusão mais fácil — e mais perigosa — neste domínio é tomar **ancoragem** por **acurácia**: um extrator pode citar um trecho verdadeiro que não responde nada. Por isso as métricas vêm em pares, e todas as que podem ser calculadas sem gente são calculadas sem IA ([[Verificador determinístico]], [[Gabaritos]]).

## As métricas

| Métrica | O que mede | Como é calculada | O que ela **não** prova |
|---|---|---|---|
| **Ancoragem** | o trecho citado existe na página citada | verificador: respostas ancoradas ÷ respostas com citação, **antes** de qualquer rebaixamento por conflito ou confiança | que a resposta responde à pergunta |
| **Acurácia** | a resposta está certa | a pergunta conta se contém **todos** os fatos obrigatórios do gabarito (`scripts/15_acuracia.py`) | que a resposta está completa; só existe onde há gabarito (2 licitações) |
| **Críticas** | acurácia nas 7 perguntas que entram no lance | o mesmo, restrito a Q1, Q5, Q9, Q12, Q13, Q14 e Q17 | — |
| **Completude** | a resposta traz o contexto: ressalva, divergência, unidade | fatos desejáveis presentes ÷ total de fatos desejáveis | que o que falta é irrelevante |
| **Conflitos detectados** | o modelo percebeu que dois documentos se contradizem | contagem de respostas com `conflito` preenchido | um número fechado — varia entre execuções idênticas |
| **Não localizado** | abstenção | respostas "não localizado" sem evidência | se a informação estava ou não no edital (a falha de recuperação se disfarça de ausência) |
| **Reprovadas** | citação que não confere | veredito REPROVADO | que as aprovadas estão certas |
| **Fila de revisão** | trabalho humano que sobra | respostas em REVISAR ou REPROVADO | que o resto dispensa olhar — é o que dispensa *procurar* |
| **Recall da recuperação** | a página da resposta entrou no contexto do RAG | para cada resposta ancorada, a página citada estava entre as recuperadas? (`46_recall_recuperacao.py`, custo zero) | a acurácia do modelo |
| **Custo por edital** | R$ por extração | tokens informados pelo provedor × tabela de preços, conferida na fatura ([[Custo por edital]]) | o custo da revisão humana |
| **Latência** | tempo de uma extração | soma do tempo das chamadas | tempo de fila e de espera por orçamento |
| **Filtro de escopo** | a regra acertou o que é folha | `p_filtro_ok` do Jev: P(folha) se a regra aceitou, 1 − P(folha) se recusou; AUC contra rótulos humanos ([[Jev — score de escopo e sustentação]]) | calibração — o Jev não é calibrado fora da distribuição |
| **Cobertura da coleta** | a rodada conseguiu olhar o PNCP | a rodada do W01 é marcada **cega** quando não consegue consultar ([[W01 Descoberta]]) | que o PNCP tem todas as licitações do país |
| **Antecedência** | tempo entre a licitação aparecer no PNCP e o fim do prazo de propostas | dias úteis entre `publicado_em` e `fim_prazo` (`49_antecedencia.py`) | quando o edital saiu no diário oficial |

## Os valores de hoje

| Métrica | Valor | Onde e quando |
|---|---|---|
| Ancoragem — licitações ativas | **98,67%** (822 de 833 respostas) | [[Página Painel]], 28/09/2026 |
| Ancoragem — histórico | **99,96%** (25.114 de 25.122) | [[Página Histórico]], 28/09/2026 |
| Fila de revisão — histórico | 5.473 respostas para revisar em 2.019 licitações extraídas (cerca de 16% das respostas) | [[Página Histórico]], 28/09/2026 |
| Revisões abertas | 5.690, em 2.009 licitações | [[Página Revisão]], 28/09/2026 |
| Acurácia — Claude Opus 5.5 | Pirapó 16/17, Bertioga 16/17 a 17/17; críticas 6/7 a 7/7 | [[Resultados medidos]], 23 e 28/09/2026 |
| Completude — Claude × GPT (Bertioga) | 37–38 de 49 × 25–26 de 49 | [[Comparação de modelos]] |
| Recall da recuperação — 12 páginas por pergunta | **100%** (Bertioga, 115 páginas) | [[RAG com BM25]] |
| Custo — Claude Opus 5.5, contexto completo | R$ 2,50 (Pirapó, v3.1) | [[Antes e depois da v3.1]] |
| Custo — produção, Claude Haiku 4.5 | R$ 0,78 (Itapecuru Mirim/MA) | [[Custo por edital]] |
| Custo — produção, GPT-6 Luna | R$ 0,20 (Itapecuru Mirim/MA) | [[Custo por edital]] |
| Filtro de escopo | probabilidade média de acerto 0,91; 2 discordâncias convictas em 1.162 licitações | [[Regras antes de IA]] |
| Antecedência | mediana de **16 dias úteis**; 94,4% com ao menos 10 (198 licitações) | 23/09/2026 |

## Como ler: piso de integridade × qualidade

> [!important] A ancoragem não separa modelos; a profundidade separa
> Em quatro medições independentes — entre Opus, Sonnet e Haiku, entre Claude e GPT, entre execuções repetidas e entre editais —, a ancoragem ficou praticamente empatada (92% a 100%), enquanto conflitos e completude abriram diferenças de duas vezes. A ancoragem é **piso de integridade**: garante que o sistema não inventa citação. Quem mede **qualidade** é o gabarito ([[Comparação de modelos]]).

- **Zero reprovadas não é zero erros.** Reprovada é citação que não existe; uma resposta aprovada pode estar ancorada e ainda assim não responder à pergunta — é para isso que existem o gabarito e o sinal "sustenta?" do Jev.
- **Erro custa mais que ausência.** Um sistema que responde 12 de 17 e admite não saber as outras 5 é melhor que um que responde 17 com 3 erradas: o primeiro é auditável, o segundo erra com confiança. Por isso "não localizado" é resposta correta e vai para revisão, em vez de ser escondido.
- **A fila de revisão é o desenho, não a falha.** Quase toda licitação tem ao menos uma resposta para olho humano (10 de 11 na medição de 23/09/2026). O modelo de operação nunca foi "o sistema resolve e a pessoa confere por amostra": é "o sistema resolve a maior parte e entrega uma fila curta e justificada" — cada item com o trecho e o link para a página. A pessoa deixa de **procurar** e passa a **conferir**.
- **Como citar cada número** está em [[Variância e como citar números]]: ancoragem e críticas pelo valor exato; custo e tempo com ±1%; acurácia com ±1 resposta em 17; conflitos sempre como faixa.

## Critério para o extrator estar em produção

Adotado antes das medições, e conferido contra elas:

| Critério | Situação |
|---|---|
| Ancoragem ≥ 95% nas respostas com citação | **atendido** — 98,67% nas ativas e 99,96% no histórico |
| As divergências conhecidas dos gabaritos detectadas automaticamente (pirâmide truncada de Bertioga, objeto divergente de Pirapó) | **atendido** — RN-09 dispara nos três modelos em Bertioga e fica em silêncio na pirâmide íntegra de Pirapó; RN-13 pega a divergência de objeto de Pirapó ([[Verificador determinístico]]) |
| Toda ausência sinalizada, nunca escondida | **atendido** — todo "não localizado" vai para revisão pela política da v3 |
| Custo por edital dentro do teto diário | **atendido** — teto de R$ 25,00 por dia com reserva de R$ 6,56 por extração ([[Custo por edital]]) |

## Relacionadas

[[MOC Avaliação]] · [[Gabaritos]] · [[Harness de avaliação]] · [[Resultados medidos]] · [[Variância e como citar números]] · [[Comparação de modelos]] · [[Verificador determinístico]] · [[Custo por edital]]
