---
tipo: decisao
familia: decisoes
adr: 2
data: 2026-09-22
decisao: aceita
status: verificado
atualizado: 2026-09-28
tags: [decisao, dados, pncp]
---

# ADR-002 — PNCP como fonte primária

> [!abstract] Em uma frase
> O **Portal Nacional de Contratações Públicas (PNCP)** é a fonte de tudo o que a solução coleta — licitações, documentos, itens, resultados e contratos —, porque tem API pública, gratuita e sem cadastro, dados abertos e obrigação legal de publicação do inteiro teor dos editais.

## Problema

Há três caminhos para descobrir licitações de folha: o PNCP, os diários oficiais e as plataformas privadas de pregão. Escolher mal é gastar esforço em fonte suja ou assumir risco jurídico sem necessidade.

## Opções

| Opção | Avaliação |
|---|---|
| **PNCP** | API pública documentada, acesso gratuito e universal, dados abertos (Lei de Acesso à Informação), manuais oficiais de integração; o inteiro teor do edital é publicado ali por obrigação (Lei 14.133, art. 54) |
| Diários oficiais | fonte não estruturada; publicam o **extrato**, não o edital; a API agregadora avaliada (Querido Diário) é instável e cobre poucos municípios da faixa que importa ([[ADR-007 Cobertura de municípios pequenos]]) |
| Plataformas privadas de pregão | termos de uso privados; risco jurídico sem necessidade |

## O que foi medido

- Todos os endpoints necessários foram testados ao vivo (22–23/09/2026).
- **Os endpoints têm confiabilidades diferentes**, e isso mudou o desenho ([[Disponibilidade do PNCP]]):

| Endpoint | Para quê | Comportamento medido |
|---|---|---|
| `api/search` | achar licitação por termo | falhas esporádicas, resolvidas com nova tentativa |
| `api/pncp/v1` (`/arquivos`, `/itens`) | baixar documento e ler item | 142 downloads sem falha num dia — mas ficou fora do ar por dias numa semana, com o erro de conexão ao banco do próprio portal no corpo da resposta |
| `api/consulta/v1` | varrer por data | três modos de falha (429, 500, queda de conexão) e truncamento silencioso |

## Escolha

O PNCP é a fonte primária. A descoberta diária usa a busca (`api/search`) e o download usa `api/pncp/v1` — os dois confiáveis; a consulta por data, instável, fica para usos que toleram atraso.

## O que custa

- **Cobertura limitada por lei até 01/04/2027** para municípios de até 20 mil habitantes ([[ADR-007 Cobertura de municípios pequenos]]).
- **Dependência de uma fonte só**: quando o PNCP cai, a coleta para. Por isso uma rodada que não consegue consultar é marcada **cega** — "nada a fazer" é diferente de "não consegui olhar" ([[W01 Descoberta]]).
- A busca textual tem defeitos (a ordenação por data não funciona); a solução não depende dela: pagina o resultado de forma explícita e deduplica pelo número de controle.

## Onde vive em produção

| Fluxo | Uso do PNCP |
|---|---|
| [[W01 Descoberta]] | busca por termo, duas consultas por termo (o ano corrente inteiro e o que está recebendo proposta), de segunda a sexta às 06:00 |
| [[W21 Baixar]] | `/arquivos` da compra: todos os documentos ativos |
| [[W41 Histórico do PNCP]] | itens, resultados, cabeçalhos e contratos com aditivos, todo dia às 04:30 |
| [[W70 Retificações]] | confere se apareceu documento novo nas licitações acompanhadas, aos domingos |

A coleta se identifica, respeita limites e nunca contorna login ou captcha ([[Legalidade da automação]]).

## O que reabriria a decisão

Uma exigência de cobertura dos municípios pequenos antes de abril de 2027, ou instabilidade prolongada do portal que comprometa o prazo das licitações.

## Relacionadas

[[MOC Decisões]] · [[Fontes de dados — PNCP]] · [[Disponibilidade do PNCP]] · [[ADR-007 Cobertura de municípios pequenos]] · [[ADR-013 Identidade de licitação é o número de controle]] · [[Legalidade da automação]]
