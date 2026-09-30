---
tipo: avaliacao
familia: avaliacao
status: verificado
atualizado: 2026-09-28
fonte_codigo:
  - scripts/fopa/verificador.py
  - scripts/fopa/extrator.py
  - scripts/14_reverificar_harness.py
  - scripts/15_acuracia.py
tags: [avaliacao, metodo, verificador, achado]
---

# A medição que mediu o medidor

> [!abstract] Em uma frase
> A primeira comparação entre modelos deu **ancoragem de 0 de 13** para o modelo mais barato; o veredito óbvio — "modelo barato não serve" — estava errado, e investigar por quê revelou **três defeitos no instrumento de medição**, não no modelo; corrigidos e remedidos sem gastar um token, viraram a regra de que uma métrica que despenca acusa primeiro o medidor.

## Papel na solução

É o episódio que fixou o método de avaliação do projeto. Ele explica por que o harness guarda a evidência de cada resposta, por que toda regra do verificador declara quando não conseguiu ler, e por que um falso positivo do verificador é tratado como defeito grave ([[ADR-011 Uma regra precisa saber quando falhou em ler]]).

## O que a métrica dizia (22/09/2026)

| Configuração | Ancoragem | Custo |
|---|---|---|
| Claude Opus 5 · high | 13/15 | R$ 4,84 |
| Claude Sonnet 5 · high | 6/15 | R$ 2,02 |
| Claude Haiku 4.5 · high | **0/13** | R$ 0,63 |

Um zero absoluto é suspeito. Qualidade ruim produz números baixos e irregulares; não produz zero em todas as respostas. **Zero uniforme é assinatura de regra, não de competência.**

## Defeito 1 — o nome do arquivo comparado byte a byte

Com a evidência guardada, a causa apareceu na primeira linha:

```text
Q1 | arq= EDITAL.pdf | pag= 1 | veredito= REPROVADO
   trecho: 'INÍCIO DA SESSÃO DE DISPUTA DE LANCES: 08/10/2026 às 09:00'
   alerta: página citada não existe: EDITAL.pdf p.1
```

O trecho está **correto e literal**; o arquivo se chama `01 - Edital - EDITAL.pdf`. Havia ainda uma segunda forma: `ARQUIVO 01 - Edital - EDITAL.pdf` — o modelo copiou o rótulo do marcador `=== ARQUIVO <nome> | PÁGINA <n> ===`, que nada dizia ser rótulo e não parte do nome. Os modelos maiores inferiram; o menor copiou o que estava escrito — o comportamento, a rigor, mais obediente dos três. O modelo mais barato foi o único a expor a ambiguidade do prompt.

**A correção, e onde ela para:** o nome citado passou a ser resolvido por apelido normalizado, **desde que resolva para um único arquivo**. Em Bertioga há três arquivos `RESPOSTA.pdf`: essa citação é de fato ambígua e continua reprovando. Tolerar o apelido resolve um problema de identificador; tolerar a ambiguidade destruiria a garantia que justifica a solução.

## Defeito 2 — a RN-09 reconhecia uma só grafia de faixa

A regra que confere a pirâmide exigia "de R$ X até R$ Y". Os documentos escrevem "R$ X a R$ Y: N", e um modelo respondeu "2.001,00 > 3.000,00: 274". Das sete faixas de Pirapó, só a última casava: a regra somava 3 contra 297 e anunciava truncamento numa pirâmide **íntegra** — nos três modelos ao mesmo tempo, porque a falha era do parser. Conferido à mão: 32 + 93 + 56 + 72 + 27 + 14 + 3 = **297**, exatamente o total. Um dos modelos chegou a escrever "soma das faixas = 297, coincide com o total impresso" — e foi reprovado por isso.

**A trava de fundo:** com menos de duas faixas reconhecidas numa resposta que descreve pirâmide, a RN-09 agora declara que **não se aplica** e pede conferência humana, em vez de deixar o silêncio passar por conferência feita.

## Defeito 3 — o separador de milhar destruído antes do casamento

A Q14 declara "1.896 vínculos". O código tirava os pontos e **depois** procurava um número com separador: "1.896" virava "1896" e casava só "189". A RN-09 comparava 1.408 contra 189 e anunciava que as faixas somavam **demais** — o oposto da verdade: a pirâmide de Bertioga está truncada e faltam **488 vínculos**, nas faixas mais altas. O defeito não escondia o alarme: **invertia a leitura dele**.

## Como os três ficaram visíveis

Nenhum apareceu numa execução isolada. Todos apareceram ao **comparar configurações**, e o sinal foi sempre o mesmo — **regularidade onde deveria haver variação**:

| Sinal observado | O que significa |
|---|---|
| 13 respostas falhando pela mesma causa | regra, não competência |
| a mesma regra disparando nos três modelos | parser, não leitura |
| zero uniforme em vez de números baixos irregulares | instrumento, não medido |

> [!important] A heurística que fica
> Quando uma métrica cai muito, ela acusa o sistema de medição antes de acusar o medido. Modelos diferentes erram de formas diferentes; quando erram igual, o que é igual entre eles é o código que os mede.

## Validação das correções — sem reexecutar nenhum modelo

| Verificação | Antes | Depois |
|---|---|---|
| Haiku · Pirapó | 0/13 | **12/13** |
| Haiku · Bertioga | 12/16 | **15/16** |
| RN-09 em Pirapó (pirâmide íntegra) | alarme nos 3 modelos | **silenciosa nos 3** |
| RN-09 em Bertioga (pirâmide truncada) | número invertido | **488 faltantes nos 3** |
| Produção da época — 7 licitações | 89/89 · 0 reprovadas | **89/89 · 0 reprovadas** |
| Custo das remedições | — | **R$ 0,00** |

## O que isso ensinou, e onde está em produção

| Lição | Onde vive hoje |
|---|---|
| toda métrica guarda a evidência que a produziu | `verificacao_respostas` guarda arquivo, página final, **página citada** e alertas de cada resposta; `verificacoes.auditoria_json` guarda a auditoria completa |
| corrigir a regra e remedir são passos separados | `versao_regras` por hash + [[W30 Reverificar em lote]], a custo zero |
| uma regra precisa saber quando falhou em ler | "RN-09 não aplicada", RN-15, "página corrigida" em vez de reprovada ([[Verificador determinístico]]) |
| instrumento literal demais reprova acerto | o comparador do gabarito normaliza horário, data por extenso e zero à esquerda, com casos de controle ([[Gabaritos]]) |

## Relacionadas

[[MOC Avaliação]] · [[Harness de avaliação]] · [[Verificador determinístico]] · [[Métricas]] · [[Comparação de modelos]] · [[ADR-011 Uma regra precisa saber quando falhou em ler]]
