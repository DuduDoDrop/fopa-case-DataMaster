---
tipo: negocio
familia: negocio
status: verificado
atualizado: 2026-09-28
fonte_codigo:
  - api/analytics.py
  - api/historico_pncp.py
  - api/contratos_pncp.py
tags: [negocio, mercado, concorrencia, analytics]
---

# Concorrência e mercado

> [!abstract] Em uma frase
> No histórico do PNCP que a solução coleta todo dia, o mercado de folha pública soma **726 compras**, **R$ 5,56 bilhões** homologados e **79 instituições** compradoras — com a Caixa e o Bradesco à frente em número de compras —; **284 licitações** morreram desertas ou fracassadas e boa parte volta ao portal; e, numa amostra medida, **três em cada quatro contratos fecham exatamente no valor mínimo**: a disputa, na maioria dos casos, não é de preço — é de **estar presente a tempo**.

## Papel na solução

Transforma a leitura de editais em vantagem competitiva: quem compra, onde, por quanto, até quando — informação que o fornecedor atual não entrega ([[Proposta de valor]]).

## O mercado, em produção (coleta de 28/09/2026)

| Medida | Valor |
|---|---|
| licitações de folha no histórico do PNCP | **2.071** |
| compradas (com vencedor) | **726** |
| valor homologado | **R$ 5,56 bilhões** |
| instituições compradoras | **79** |
| desertas ou fracassadas | **284** |

| Instituição | Compras | Valor | Ticket médio | Participação (nº) |
|---|---|---|---|---|
| Caixa Econômica Federal | 224 | R$ 838,75 mi | R$ 3,74 mi | 30,6% |
| Bradesco | 195 | R$ 1,24 bi | R$ 6,36 mi | 26,6% |
| Santander | 68 | R$ 596,79 mi | R$ 8,78 mi | 9,3% |
| Itaú Unibanco | 48 | R$ 334,83 mi | R$ 6,98 mi | 6,5% |
| Banco do Brasil | 35 | R$ 1,11 bi | R$ 31,79 mi | 4,8% |
| Banrisul | 15 | R$ 1,25 bi | R$ 83,35 mi | 2,0% |

Regras do cálculo: a instituição é o CNPJ-raiz; homologação cancelada não conta; compra cadastrada duas vezes conta uma; homologado simbólico (até R$ 1) vale pelo contrato ([[Página Analytics de Mercado]]).

## O que os números dizem

- **Poucos compram muito, muitos compram pouco.** Os tickets médios vão de R$ 3,7 milhões a R$ 83 milhões entre os seis maiores: bancos públicos regionais compram poucas folhas grandes; os nacionais, muitas folhas de todos os portes.
- **As cooperativas de crédito são concorrentes reais**, sobretudo em municípios pequenos: numa amostra de 61 vencedores (23/09/2026), elas eram 28% (Sicredi, Sicoob, Cresol e outras), e os maiores ágios observados vinham delas.
- **A disputa raramente é de preço.** Na mesma amostra, **74% dos contratos homologaram exatamente no valor mínimo**, com ágio mediano de 1,00× para bancos públicos, privados e cooperativas; o máximo observado foi 1,93×. A alavanca principal é **estar presente e ler a tempo** — o contrato que se perde é o que ninguém leu a tempo.
- **O que morre volta.** 437 licitações foram publicadas de novo; 236 foram compradas depois da republicação e 201 ainda não têm comprador ([[Página Analytics Histórico FOPA]]). Deserta e fracassada são oportunidade, não fim.
- **Os contratos dizem quando o órgão licita de novo.** Na primeira coleta de contratos (27/09/2026): 1.396 contratos, 1.231 vigentes e **220 vencendo nos 12 meses seguintes** ([[ADR-023 O histórico e os contratos do PNCP todo dia]]).

## Os concorrentes e o tempo

> [!info] Informado pelo banco
> Concorrentes têm software próprio que lê a API do PNCP — e a API disponibiliza licitações e documentos, em vários casos, **antes** da data de publicação.

A solução lê o mesmo portal, pelo mesmo caminho, todo dia útil às 06:00 e a qualquer hora pelo botão — tira o banco da posição de receber a informação três dias depois ([[Ganho para o negócio]]).

## Contratação direta: um mercado que mudou de status

Parte das folhas vai a banco público por **contratação direta** (dispensa ou inexigibilidade). Em agosto de 2026, o **TCE-MG** julgou irregular a contratação direta de folha sob a Lei 14.133 — atividade econômica, sujeita a licitação, sem privilégio para banco oficial. É mercado que hoje se perde sem disputa e que passou a ser questionável ([[Jurisprudência — tribunais de contas]]).

## O que a análise ainda não faz

A comparação com a carteira atual do banco (quantas folhas ele tem, em quais órgãos, com que retenção) depende de dado interno; o **ágio** e o **valor por servidor** por região e porte são a próxima camada do Analytics ([[Próximos passos]]).

## Relacionadas

[[MOC Negócio]] · [[Página Analytics de Mercado]] · [[Página Analytics Histórico FOPA]] · [[W41 Histórico do PNCP]] · [[Cessão onerosa da folha - fundamentos]] · [[Problema de negócio]]
