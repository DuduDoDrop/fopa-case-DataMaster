---
tipo: pagina
familia: site
rota: "/analytics/historico-fopa"
papel_minimo: usuario
status: verificado
atualizado: 2026-09-29
fonte_codigo:
  - web/src/paginas/AnalyticsHistorico.tsx
  - api/analytics.py
tags: [site, pagina, analytics, republicacao, oportunidade]
---

# Página Analytics Histórico FOPA

> [!abstract] Em uma frase
> As licitações de folha que **voltaram a ser publicadas** porque a tentativa anterior não terminou em compra — deserta, fracassada, revogada ou sem resultado —, com a cadeia de tentativas de cada órgão e o desfecho: ainda sem comprador ou comprada depois de republicar.

## Papel na solução

Licitação deserta **volta**: a folha continua precisando de banco. Quem sabe primeiro chega antes — e chega sabendo quantas vezes ninguém quis e em que condições. Esta página transforma o histórico do PNCP numa **lista de oportunidades de segunda chance** ([[Problema de negócio]]).

![[site-analytics-historico-fopa.jpg]]

## O que a página mostra (em produção, 28/09/2026)

| Quadro | Valor |
|---|---|
| publicados de novo | **437** |
| ainda sem comprador | **201** |
| comprados depois de republicar | **236** |

A tabela "Editais sem comprador publicados novamente" traz, para cada cadeia: **onde** (município/UF e órgão), **publicações** ("6ª publicação"), o **histórico** de cada tentativa com a data e o desfecho (em aberto, deserta, comprada…) e a **situação** atual ("comprada na 6ª", "sem comprador").

## Como a cadeia é montada

O PNCP **não** liga uma republicação à anterior; a cadeia é uma **heurística** documentada:
- mesmo órgão;
- publicações em ordem de data;
- a tentativa seguinte continua a cadeia se a anterior **não** terminou comprada e veio **em até 540 dias**;
- o mesmo edital cadastrado duas vezes (mesmo dia, valor a menos de 1% de diferença) é **uma** tentativa.

Só entra o que a IA confirma como folha; as tentativas contam o histórico inteiro, e o período filtra pela **última** publicação.

## Filtros

- **Busca** por município, UF, órgão ou controle.
- **Período** (última publicação): Todo o histórico · Último mês · 3 meses · 6 meses · 1 ano · 2 anos · 4 anos.
- **Tentativas:** todas · 2 · 3 · 4 ou mais.
- **Mostrar:** 10, 50, 100 ou todos.

## De onde vêm os dados

`GET /api/analytics?…` (a parte de republicações) sobre as tabelas `pncp_*` coletadas pelo [[W41 Histórico do PNCP]].

## Quem vê

Todo usuário logado. A troca entre esta página e a [[Página Analytics de Mercado]] é pelos dois botões no topo.

## Relacionadas

[[MOC Site]] · [[Página Analytics de Mercado]] · [[W41 Histórico do PNCP]] · [[Concorrência e mercado]] · [[Problema de negócio]]
