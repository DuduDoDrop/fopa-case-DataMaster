---
tipo: avaliacao
familia: dados
status: verificado
atualizado: 2026-09-28
fonte_codigo:
  - scripts/fopa/pncp.py
  - scripts/65_disponibilidade.py
  - n8n/workflows/W01.json
  - n8n/workflows/W21.json
tags: [dados, pncp, resiliencia, disponibilidade]
---

# Disponibilidade do PNCP

> [!abstract] Em uma frase
> O PNCP é **gratuito e obrigatório por lei, mas não é sempre confiável**: são três serviços com disponibilidade independente, e o que entrega os documentos já ficou fora do ar por dias; a solução trata isso como requisito — espera e repete, registra a rodada **cega**, retoma depois — em vez de acidente.

## Papel na solução

Uma licitação tem data de sessão, e ela não espera o portal voltar. Saber **como** a fonte falha decide a estratégia: contra bloqueio por uso, reduzir a frequência; contra fragilidade do servidor, insistir espaçado no tempo. Confundir as duas levaria a desligar um caminho que funciona.

## O que foi medido

| Serviço | Para quê | Comportamento observado |
|---|---|---|
| `api/search` | achar licitações por termo | rápido (~0,1 s); falhas esporádicas, resolvidas na nova tentativa |
| `api/pncp/v1` | documentos, itens, resultados, contratos | **fora do ar por dias** numa semana de construção, com `504` depois de 45 s; no mesmo mês, um dia com 142 downloads sem falha; itens e resultados a ~0,1 s por chamada, sem limitação |
| `api/consulta/v1` | cabeçalhos e varredura por data | três modos de falha — `429` (espera), `500` (repetir), queda de conexão (desistir e voltar) — e **página curta no meio** do conjunto; limitou a 5 pedidos por minuto numa manhã e respondeu em 1 s à tarde |

> [!fato] A causa aparece no próprio erro
> As quedas do `api/pncp/v1` vinham com a mensagem de falha ao obter conexão com o banco do próprio portal — uma exceção **transitória**: não é bloqueio por uso nem manutenção planejada. A estratégia certa é insistir ao longo de horas e dias, não dentro do minuto.

- **Não há limite de requisição declarado** no `api/pncp/v1`: nas respostas não aparecem cabeçalhos de cota nem `Retry-After`, e o manual não documenta cota. Os cabeçalhos autorizam cache de 2 minutos e não mantêm conexão aberta — o que desaconselha paralelismo agressivo.
- **Um `400` rápido é serviço de pé recusando a pergunta;** um `504` depois de 45 s é serviço morto. Os dois não pedem a mesma reação.

## Como a solução se protege

| Mecanismo | Onde |
|---|---|
| espera de 30 s e **uma** nova tentativa em 429, 5xx e rede, dentro do fluxo | [[W01 Descoberta]], [[W21 Baixar]], [[W70 Retificações]] |
| cada página da busca é **gravada antes** de pedir a próxima: um erro no meio não apaga o que já foi lido | `buscas_paginas` ([[Modelo de dados]]) |
| a rodada que não conseguiu consultar é marcada **cega** — diferente de "nada a fazer" — e aparece em Execuções e Saúde | [[Página Execuções]], [[Página Saúde]] |
| a falha de download vira `falha_rede`, com **espera crescente** (15 min → 2 h → 12 h) e nova tentativa pela fila | [[W10 Fila]], [[Funções e views do banco]] |
| **disjuntor:** 3 ou mais erros do processamento em 30 minutos sem sucesso param a fila | `fn_disjuntor_w20_aberto` |
| o histórico e os contratos têm limite de **tempo**, não de meta: o que sobra fica para o dia seguinte | [[W41 Histórico do PNCP]] |
| a coleta de cabeçalhos da API de consulta roda **depois** da descoberta, para não disputar o limite por IP | [[Decisões de construção da v3]] |
| o retorno de `/itens` é guardado inteiro, porque a API já provou cair | `itens_api` |

## A promessa que se apoia em qual serviço

O aviso de licitação nova usa a busca e os documentos — os dois serviços confiáveis no dia a dia. A varredura completa por data, que mediria o recall contra "todas as licitações", depende do serviço instável; por isso o recall absoluto da coleta não é prometido, e a cobertura é **declarada por rodada** ([[ADR-007 Cobertura de municípios pequenos]]).

## Relacionadas

[[MOC Dados]] · [[Fontes de dados — PNCP]] · [[W01 Descoberta]] · [[W21 Baixar]] · [[Consciência operacional]] · [[ADR-002 PNCP como fonte primária]] · [[ADR-012 Segundo provedor de modelo]]
