---
tipo: referencia
familia: dados
status: verificado
atualizado: 2026-09-28
fonte_codigo:
  - scripts/fopa/escopo.py
  - api/escopo_ajuste.py
  - db/012_seed.sql
  - db/018_recorte_2026.sql
tags: [dados, escopo, negocio, folha]
---

# Escopo — o que é licitação de folha

> [!abstract] Em uma frase
> Uma licitação de folha é aquela em que um órgão público **vende a um banco o direito de processar e pagar os salários dos seus servidores** — cessão onerosa, centralização ou processamento dos créditos da folha, inclusive por credenciamento ou contratação direta —; o que gira **em volta** da folha (software, consultoria, consignado isolado, tarifa que o órgão paga) não é.

## Papel na solução

É a definição que separa o que o banco quer comprar do ruído do portal. Ela decide o que entra no painel, o que vai para a extração paga e o que aparece no mercado do Analytics. A mecânica da decisão está em [[Regras antes de IA]]; esta nota é o conceito e os números.

## O que é e o que não é

| É licitação de folha | Não é |
|---|---|
| **cessão onerosa** do direito de pagar a folha (o banco paga ao órgão) | **software** de folha, licença de uso, migração de dados, backup |
| **processamento e gerenciamento de créditos** provenientes da folha | **consultoria**, auditoria, estudo de viabilidade sobre a folha |
| **centralização** da folha e dos serviços bancários do órgão, com exclusividade | **consignado** oferecido como produto isolado |
| contratação de **instituição financeira** para operar a folha, com consignado como serviço agregado | **tarifa bancária** que o órgão paga, envio e retorno de arquivos, conta institucional que exclui a folha |
| **credenciamento** de instituições financeiras para os créditos da folha | contabilidade terceirizada, RH, ponto eletrônico, programa de estágio |
| folha de benefícios do regime próprio de previdência | obra, locação, compra de bens, eventos e cursos "sobre a folha" |

A distinção que organiza tudo: na cessão, o município **recebe** dinheiro do banco; na terceirização, o município **paga** uma empresa. Fluxos financeiros opostos — e o objeto quase sempre denuncia qual é pelo que contrata ([[Cessão onerosa da folha - fundamentos]]).

## Modalidades que entram

Nenhuma modalidade é descartada automaticamente. Numa amostra de 100 licitações de folha (22/09/2026):

| Modalidade (campo normalizado do PNCP) | % |
|---|---|
| Pregão eletrônico | 65% |
| Dispensa | 15% |
| Credenciamento | 8% |
| Pregão presencial | 7% |
| Inexigibilidade | 3% |
| Concorrência eletrônica | 2% |

**35% não é pregão eletrônico** — restringir a ele descartaria um terço do mercado. E **98% é municipal**.

## Como a solução encontra essas licitações

1. **Seis termos de busca** no PNCP, escolhidos para varrer o vocabulário real dos objetos ("cessão onerosa folha de pagamento", "créditos provenientes da folha de pagamento", "folha de pagamento servidores instituição financeira" e outros três — [[Fontes de dados — PNCP]]). "Cessão onerosa" sozinho, o termo tecnicamente correto, aparece em só 13% dos objetos; "folha de pagamento" em 73%.
2. **A regra de escopo** decide cada resultado, com motivo e versão; uma camada de ajuste só tira o que é serviço em volta da folha ([[Regras antes de IA]]).
3. **O Jev** dá uma segunda opinião, primeiro com o objeto e depois com o edital; discordância convicta vai para rótulo humano ([[Jev — score de escopo e sustentação]]).
4. **O rótulo humano** prevalece na tela.

## O recorte de tempo

O painel e a extração paga cobrem licitações com **sessão em 2026 ou depois** (sem data de sessão, publicadas em 2026). O passado não é descartado: entra como **histórico**, alimenta o Analytics e serve para calibrar preço ([[ADR-015 Acervo só de 2026 e só compra de folha]]).

| Estado ao registrar | Quando |
|---|---|
| `nova` | no escopo, no recorte, sessão aberta — vai para a fila |
| `fora_escopo` | a regra recusou — fica para o sinal do Jev e o rótulo humano, nunca para a fila |
| `fora_janela` | no escopo, sessão já passada — histórico |
| (não gravada) | fora do recorte, na descoberta diária |

## Os números em produção (28/09/2026)

| Onde | Quantas |
|---|---|
| Painel — licitações de folha em andamento | **71** |
| Histórico — licitações de folha | **2.020** (1.433 anteriores a 2026) |
| Analytics — licitações de folha no histórico do PNCP | **2.071**, das quais 726 compradas por 79 instituições |
| Aba Escopo — licitações rotuladas por humanos | 281 |

## Relacionadas

[[MOC Dados]] · [[Regras antes de IA]] · [[Fontes de dados — PNCP]] · [[Problema de negócio]] · [[Cessão onerosa da folha - fundamentos]] · [[ADR-001 Escopo somente setor público]] · [[ADR-003 Classificação por regras antes de IA]] · [[ADR-015 Acervo só de 2026 e só compra de folha]]
