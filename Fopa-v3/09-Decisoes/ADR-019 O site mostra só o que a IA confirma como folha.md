---
tipo: decisao
familia: decisoes
adr: 19
data: 2026-09-25
decisao: aceita
status: verificado
atualizado: 2026-09-28
tags: [decisao, site, jev, escopo]
---

# ADR-019 — O site mostra só o que a IA confirma como folha

> [!abstract] Em uma frase
> O Painel, o Histórico e o Analytics mostram **sempre** só o que é folha pela regra **e** não é recusado pela IA — sem caixa de seleção e sem aviso —; o que o filtro tira não é apagado e volta no Analytics com "mostrar fora do escopo", e o rótulo humano "é folha" traz de volta qualquer licitação.

## Problema

O filtro "apenas FOPA (a IA confirma)" existia como caixa desligada por padrão no Histórico e no Analytics: escondia o que a IA estima que não é folha (nota abaixo de 50%). Desligado, o usuário via ruído; com a caixa, precisava lembrar de ligá-la.

## Opções

| Opção | Avaliação |
|---|---|
| caixa desligada por padrão | ruído na tela para quem não sabe da caixa |
| caixa ligada por padrão | uma escolha a mais na tela, sem ganho |
| **filtro sempre aplicado, sem caixa; o fora do escopo acessível no Analytics** | adotado ("menos é mais") |

## Escolha

- **Painel e Histórico:** listas e quadros sempre com o filtro.
- **Analytics:** padrão "folha pela regra **e** confirmada pela IA"; a caixa **"mostrar fora do escopo"** traz de volta o que a regra recusou e o que a IA não confirma.
- Licitação **sem nota** da IA aparece (a IA ainda não olhou); o **rótulo humano** "é folha" prevalece sobre a nota.
- O quadro das discordâncias do Jev compara com o **escopo que a tela mostra** (o rótulo humano manda).
- Na mesma rodada de simplificação, a página "Questionário" saiu do site; as respostas do questionário no detalhe de cada licitação ficam ([[Questionário — as 17 perguntas]]).

## O que foi medido

Com o filtro e os rótulos humanos, as discordâncias do Jev na tela zeraram: em 28/09/2026, "Não reconhecidas como folha pela IA" em **0 de 76** no Painel (nota média 92%) e **0 de 2.015** no Histórico (93%).

## O que custa

Uma licitação que a IA recusa com nota abaixo de 50% some do Painel e do Histórico até alguém rotulá-la — mitigado porque o rótulo humano prevalece e a aba Escopo mostra as candidatas.

## Onde vive em produção

`api/consultas.py` (as consultas das telas usam o escopo efetivo e a média das notas do Jev); `fn_ia_nao_fopa` no banco ([[Jev — score de escopo e sustentação]], [[Página Painel]], [[Página Histórico]], [[Página Analytics de Mercado]]).

## O que reabriria a decisão

Evidência de que o filtro esconde folha legítima com frequência — os rótulos humanos da aba Escopo são o termômetro.

## Relacionadas

[[MOC Decisões]] · [[Jev — score de escopo e sustentação]] · [[Regras antes de IA]] · [[ADR-015 Acervo só de 2026 e só compra de folha]] · [[Página Revisão]]
