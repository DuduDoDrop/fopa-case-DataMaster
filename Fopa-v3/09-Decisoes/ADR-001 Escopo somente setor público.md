---
tipo: decisao
familia: decisoes
adr: 1
data: 2026-09-22
decisao: aceita
status: verificado
atualizado: 2026-09-28
tags: [decisao, escopo, negocio]
---

# ADR-001 — Escopo somente setor público

> [!abstract] Em uma frase
> A solução cobre **só folhas de pagamento do setor público** — prefeituras, estados, Distrito Federal, autarquias, fundações, tribunais, câmaras e estatais —, porque só ali a compra da folha é **publicada por obrigação legal**, num portal nacional com API aberta.

## Problema

O mercado de folha inclui empresas privadas, mas o regime jurídico, o canal de publicação e o ciclo de venda são completamente diferentes. Automatizar a descoberta e a leitura exige um insumo público, estruturado e completo.

## Opções

| Opção | Avaliação |
|---|---|
| Incluir folha privada | não há fonte pública: é negociação bilateral, sem edital nem portal — seria outro produto, de prospecção comercial |
| Só municípios | perderia estados, tribunais e câmaras, que têm folhas grandes |
| **Todo o setor público** | a publicidade é obrigatória (Lei 14.133/2021, art. 54) e centralizada no PNCP, com API pública |

## O que foi verificado

- Numa amostra de 100 licitações de folha (22/09/2026), **98% eram municipais** — o setor público municipal é o mercado.
- As estatais entram por regime próprio (Lei 13.303/2016), com regras de licitação distintas ([[Lei 13.303-2016 - estatais]]).

## Escolha

A solução cobre **apenas** folha do setor público. Empresas privadas estão fora de escopo, de forma explícita.

## O que custa

- Deixa de fora um mercado relevante — o de folha privada, que depende de relacionamento comercial, não de edital.
- Estatais exigem atenção ao regime da Lei 13.303.

## Onde vive em produção

- A fonte é o PNCP, que só publica contratações públicas ([[ADR-002 PNCP como fonte primária]]).
- A regra de escopo decide o que é **compra de folha** dentro do setor público ([[Regras antes de IA]]).
- O Analytics mostra o mercado por órgão comprador e por instituição financeira compradora ([[Página Analytics de Mercado]]).

## O que reabriria a decisão

A decisão do banco de prospectar folha privada — que seria um produto diferente, sem edital para ler.

## Relacionadas

[[MOC Decisões]] · [[Problema de negócio]] · [[Escopo — o que é licitação de folha]] · [[Lei 14.133-2021 - visão geral]] · [[Lei 13.303-2016 - estatais]]
