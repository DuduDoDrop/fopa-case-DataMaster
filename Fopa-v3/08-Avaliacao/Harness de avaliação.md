---
tipo: referencia
familia: avaliacao
status: verificado
atualizado: 2026-09-28
fonte_codigo:
  - scripts/11_avaliar.py
  - scripts/13_reverificar.py
  - scripts/14_reverificar_harness.py
  - scripts/15_acuracia.py
  - scripts/17_benchmark.py
  - scripts/21_adversarial.py
  - scripts/22_recall.py
  - scripts/27_orcamento_openai.py
  - scripts/28_baixar_licitacao.py
  - scripts/34_placar.py
  - scripts/35_antes_depois.py
  - scripts/46_recall_recuperacao.py
  - scripts/58_preco_openai.py
  - scripts/82_gastos_ia.py
tags: [avaliacao, harness, metodo, reprodutibilidade]
---

# Harness de avaliação

> [!abstract] Em uma frase
> O conjunto de ferramentas e o protocolo com que cada número do projeto foi produzido: o **mesmo edital**, lido **uma vez**, passado por várias configurações (modelo, esforço, modo, repetições), com a **evidência de cada resposta guardada**, a acurácia medida contra gabarito, o custo conferido na fatura — e a possibilidade de **remedir a custo zero** quando uma regra muda.

## Papel na solução

É o que transforma decisões de IA em experimentos. Sem ele, "Claude ou GPT?", "RAG ou contexto completo?", "esforço alto ou médio?" seriam opinião. Com ele, cada decisão da família [[MOC Decisões]] cita a medição que a sustentou. E o código medido é o **mesmo** que roda em produção: o worker monta o prompt com as funções do núcleo `scripts/fopa`, que o harness também usa ([[Prompt do extrator]]).

## As ferramentas

| Script | O que faz | Custo |
|---|---|---|
| `11_avaliar.py` | o harness: varre modelos, esforços e modos sobre o **mesmo** edital, com repetições para medir variância; o OCR roda uma vez e é reaproveitado em todas as configurações | chamadas de modelo |
| `15_acuracia.py` | acurácia, críticas e completude contra os [[Gabaritos]] | R$ 0,00 |
| `17_benchmark.py` | consolida as extrações por modelo através das licitações, e emite o **recorte comparável** (só as licitações em que todos rodaram) | R$ 0,00 |
| `34_placar.py` | o placar de modelos num edital, com o custo real atribuído pela fatura quando os tokens batem | R$ 0,00 |
| `35_antes_depois.py` | a medição da v3.1 (ordem do prompt e Best-of-N), com **modo seco** que estima o gasto montando os prompts reais sem chamar modelo, e **teto** que para antes de estourar | chamadas de modelo (R$ 23,79 medidos contra R$ 24,22 estimados) |
| `22_recall.py` · `46_recall_recuperacao.py` | recall da recuperação por `k`, contra o gabarito ou contra as respostas ancoradas | R$ 0,00 |
| `13_reverificar.py` · `14_reverificar_harness.py` | reaplicam o verificador às extrações já feitas (produção e harness) | R$ 0,00 |
| `21_adversarial.py` | bateria de editais sintéticos com defeito plantado, mais um caso de controle sem defeito ([[Injeção de prompt e defesas]]) | R$ 0,00 no modo simulado |
| `27_orcamento_openai.py` | conta os tokens antes de gastar (errou 1,1% em Pirapó) | R$ 0,00 |
| `58_preco_openai.py` · `82_gastos_ia.py` | preço derivado da fatura; gasto real por provedor pela API administrativa ([[Custo por edital]]) | R$ 0,00 |
| `28_baixar_licitacao.py` | baixa os documentos de uma licitação pelo número de controle, com o filtro de escopo **antes** do download | R$ 0,00 |

## O protocolo

1. **Gabarito primeiro.** Sem gabarito, só dá para medir ancoragem e concordância.
2. **Uma variável por vez.** Varrer modelo e modo juntos impede atribuir a causa.
3. **O mesmo insumo.** O OCR é feito uma vez e reaproveitado; senão, comparar seis configurações custaria seis leituras e misturaria ruído de preparação com o efeito medido.
4. **Repetir para medir a variância.** Uma execução não é uma medição; n = 3 na mesma configuração mostrou o que é estável e o que varia ([[Variância e como citar números]]).
5. **Custo junto com a acurácia.** Acurácia sem custo não é decisão.
6. **A configuração faz parte do resultado.** Cada execução registra provedor, modelo, esforço e modo: sem isso, dois números diferentes não dizem se mudou o modelo ou a configuração.
7. **A evidência fica com o número.** Cada execução guarda, por resposta, arquivo, página, trecho e os alertas do verificador, e imprime as causas de falha agrupadas.
8. **Toda métrica tem um caso de controle** com resultado conhecido — a bateria adversarial tem um edital sem defeito; o comparador do gabarito tem casos que **não** podem casar ("5" em "25").

> [!important] Por que guardar a evidência mudou tudo
> O harness nasceu guardando só o texto das respostas. Na primeira comparação entre modelos, a ancoragem de um deles deu **0 de 13** — e não havia como saber por quê. Com a evidência salva, a causa apareceu numa linha: "página citada não existe: EDITAL.pdf p. 1" treze vezes — a regra, não o modelo ([[A medição que mediu o medidor]]).

## Remedir sem pagar de novo

Como o [[Verificador determinístico]] não usa IA e o texto de cada página fica congelado, **mudar uma regra e remedir o efeito são passos separados e gratuitos**: os scripts de reverificação reaplicam as regras novas às respostas já pagas. Reexecutar o modelo mudaria duas coisas ao mesmo tempo — a regra e a amostra — e traria a variância da geração para dentro da medição. Em produção, o mesmo princípio é o [[W30 Reverificar em lote]].

## A concordância, sem gabarito

Onde não há gabarito, a **concordância** entre configurações é o melhor sinal disponível: duas leituras independentes chegando à mesma resposta num campo crítico é evidência fraca, mas real. Ela não distingue, porém, **discordar** de **responder recortes diferentes do mesmo fato**:

> [!example] A Q17 de Pirapó/RS — os dois "discordantes" estavam certos
> Um modelo respondeu "não localizada exigência de garantia"; outro, "o edital menciona garantia de proposta e garantia prestada". A busca literal no texto mostrou que não há cláusula exigindo garantia (o primeiro está certo) **e** que o edital pune a perda de uma garantia que nunca exigiu (o segundo apontou uma contradição do documento). A divergência foi gatilho de conferência, não veredito — e virou um fato do gabarito.

## Onde estão os insumos

- O código de todas as ferramentas está no repositório, em `scripts/`.
- As medições do Jev estão em `docs/medicoes/` (JSON por experimento, com data).
- Os editais medidos são documentos públicos do PNCP e **não** vão no repositório (só um conjunto de teste em `amostras/_fixture`); para remedir, baixam-se pelo número de controle com `28_baixar_licitacao.py`. Os resultados de cada medição estão registrados nas notas desta família, com data e script.

## Relacionadas

[[MOC Avaliação]] · [[Métricas]] · [[Gabaritos]] · [[Resultados medidos]] · [[Variância e como citar números]] · [[A medição que mediu o medidor]] · [[Testes e CI]] · [[Verificador determinístico]]
