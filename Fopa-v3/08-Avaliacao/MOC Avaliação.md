---
tipo: moc
familia: avaliacao
status: verificado
atualizado: 2026-09-28
tags: [moc, avaliacao, metricas]
---

# MOC Avaliação

> [!abstract] Em uma frase
> Como a solução é medida: métricas que separam **integridade** (a citação existe) de **qualidade** (a resposta está certa e completa), dois gabaritos humanos de fatos, um harness que varia uma coisa por vez e guarda a evidência, a variância medida — e os resultados, com data, da primeira extração até a produção.

## Papel na solução

Toda decisão de IA do projeto — modelo, modo de contexto, esforço, ordem do prompt, Best-of-N — foi tomada **depois** de medida, com o mesmo código que roda em produção. Esta família é onde estão os instrumentos e os números; a família [[MOC Decisões]] é onde eles viram escolha.

## As notas

| Nota | O que responde |
|---|---|
| [[Métricas]] | o que cada métrica mede e o que ela **não** prova; os valores de hoje; o critério para o extrator estar em produção |
| [[Gabaritos]] | as duas licitações lidas integralmente, os fatos exigidos em cada pergunta e as armadilhas |
| [[Harness de avaliação]] | as ferramentas, o protocolo e a remedição a custo zero |
| [[Resultados medidos]] | o índice de tudo o que foi medido, por tema e com data, incluindo a produção em 28/09/2026 |
| [[Comparação de modelos]] | seis modelos, dois fornecedores, dois editais: a ancoragem empata, a profundidade separa |
| [[Antes e depois da v3.1]] | a remedição da ordem do prompt e do Best-of-N |
| [[Variância e como citar números]] | o que é estável, o que varia, e como afirmar cada número |
| [[A medição que mediu o medidor]] | o 0 de 13 que era defeito do instrumento — e o método que nasceu dele |

## O que a família mostra, em quatro linhas

1. **A citação é confiável:** 99,96% das respostas do histórico têm o trecho conferido na página citada, por uma verificação sem IA.
2. **A qualidade tem número:** contra gabarito humano, o extrator Claude acerta 16 a 17 de 17 e as críticas, também no edital difícil.
3. **O custo é previsível e caiu:** R$ 2,50 por edital no Claude em contexto completo, um terço a menos que antes da v3.1, com custo e tempo repetindo em 1%.
4. **O que varia está declarado:** conflitos entre documentos são descoberta, variam 19% entre execuções idênticas e são citados como faixa.

## Relacionadas

[[Home]] · [[MOC IA]] · [[MOC Decisões]] · [[Verificador determinístico]] · [[Visão geral da solução]] · [[Testes e CI]]
