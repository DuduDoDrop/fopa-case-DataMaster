---
tipo: etica
familia: seguranca-e-etica
status: verificado
atualizado: 2026-09-28
fonte_codigo:
  - scripts/fopa/pncp.py
  - n8n/workflows/W01.json
  - n8n/workflows/W21.json
  - n8n/workflows/W41.json
tags: [etica, legal, compliance, coleta, automacao]
---

# Legalidade da automação

> [!abstract] Em uma frase
> A solução **não raspa portal nenhum**: consome as **APIs oficiais e documentadas do PNCP**, cujo consumo automatizado é o uso pretendido pelo órgão e exigido pela Lei de Acesso à Informação, identificando-se em cada pedido, com esperas conservadoras, coleta mínima e nenhum controle de acesso contornado.

## Papel na solução

A primeira pergunta de uma área de compliance é "vocês vão raspar sites do governo?". A resposta precisa ser melhor que "é tudo público" — e o risco que mais pesa não é o jurídico, é o **reputacional**: a instituição que usa a ferramenta disputa licitações nesses mesmos municípios.

## O fundamento

| Fundamento | Texto e consequência |
|---|---|
| **PNCP — acesso** | o acesso é gratuito e universal, sem cadastro, usuário ou senha para consultas |
| **PNCP — dados abertos** | o portal adota o formato de dados abertos e observa a Lei 12.527/2011 (LAI); a publicidade nele é obrigatória a todos os entes pela Lei 14.133/2021 (art. 174) |
| **LAI, art. 8º, §3º, III** | os sítios devem *"possibilitar o acesso automatizado por sistemas externos em formatos abertos, estruturados e legíveis por máquina"* — o inciso não só permite: **obriga** o órgão a possibilitar o acesso por sistema |
| **API para máquina** | o próprio portal publica manuais e a especificação das APIs para consulta automatizada — consumo automatizado é o uso **pretendido**, não um desvio de finalidade |
| **O reuso** | autorizado pelo regime legal de publicidade, não por um termo de serviço (não há licença própria declarada) |

## As regras de conduta, cumpridas

| Regra | Como é cumprida |
|---|---|
| **Só API documentada, nunca HTML** | não há raspador de página na solução: busca, documentos, itens, resultados e contratos vêm das APIs públicas ([[Fontes de dados — PNCP]]) |
| **Identificação** | todo pedido leva um `User-Agent` que diz o nome do sistema, a finalidade e um contato |
| **Ritmo conservador** | esperas de 30 s e uma nova tentativa em 429/5xx; reprocessamento com espera crescente pela fila; disjuntor quando o processamento falha em série; pausa entre licitações no histórico; a consulta mais sensível ao limite roda fora da janela da descoberta ([[Disponibilidade do PNCP]]) |
| **Coleta mínima** | a regra de escopo roda **antes** do download: só licitações de folha têm documentos baixados; o portal não é espelhado |
| **Origem e integridade** | cada arquivo guarda a URL de origem, a data e o SHA-256 |
| **Nada contornado** | não há login, captcha ou paywall no caminho, e nenhum código tenta contornar autenticação |

## Fontes que ficaram de fora, e por quê

| Fonte | Situação |
|---|---|
| plataformas privadas de pregão | termos de uso próprios podem vedar coleta automatizada; quando a plataforma integra com o PNCP, a licitação é coletada **pelo PNCP** |
| agregador de diários oficiais | dados livres, mas a API é instável e o uso como infraestrutura de produto é zona cinzenta nos termos; e o diário traz o extrato, não o edital ([[ADR-007 Cobertura de municípios pequenos]]) |

## O que depende do banco

Numa operação do banco, o contato do `User-Agent` passa a ser o institucional; a política interna de uso de IA com documentos externos é normativo do banco ([[Privacidade e LGPD]]).

## Relacionadas

[[MOC Segurança e Ética]] · [[Fontes de dados — PNCP]] · [[Disponibilidade do PNCP]] · [[Privacidade e LGPD]] · [[ADR-002 PNCP como fonte primária]] · [[Lei 14.133-2021 - visão geral]] · [[MOC Legal]]
