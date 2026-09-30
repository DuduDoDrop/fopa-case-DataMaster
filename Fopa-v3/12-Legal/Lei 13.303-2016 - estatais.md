---
tipo: legal
familia: legal
status: verificado
atualizado: 2026-09-28
fontes:
  - https://www.planalto.gov.br/ccivil_03/_ato2015-2018/2016/lei/l13303.htm
  - https://www.gov.br/compras/pt-br/acesso-a-informacao/comunicados/2023/Informaessestatais.pdf
tags: [legal, estatais, lei-13303]
---

# Lei 13.303/2016 — estatais

> [!abstract] Em uma frase
> Empresas públicas e sociedades de economia mista **não seguem a Lei 14.133**: têm estatuto próprio (Lei 13.303/2016), que exige licitação e transparência permanente; publicam no PNCP por força de norma orçamentária — e, no acervo medido, **nenhuma licitação de folha veio de estatal**.

## Papel na solução

Estatais têm folha e poderiam licitá-la; a solução cobre o setor público inteiro ([[ADR-001 Escopo somente setor público]]). Esta nota diz por que elas chegam por outro regime e o que foi medido sobre elas.

## O regime

| Ponto | O que vale |
|---|---|
| lei aplicável | Lei 13.303/2016 — a Lei 14.133 não alcança empresas públicas, sociedades de economia mista e subsidiárias |
| licitação | exigida para serviços, aquisição e locação de bens, alienação de bens e ativos e obras |
| transparência | documentos divulgados na internet de forma permanente e cumulativa |
| PNCP | a Lei 13.303 é anterior ao portal; a obrigação de publicar contratos no PNCP veio pelo art. 17 da Lei 14.436/2022 (LDO de 2023) |
| garantia | art. 70: até **5%**, elevado a **10%** em grande vulto com complexidade técnica e riscos elevados — o mesmo teto da Lei 14.133 ([[Garantia contratual]]) |

## O que foi medido

Num corpus de 329 licitações coletadas com o termo "folha de pagamento" (23/09/2026), **2 órgãos** tinham padrão de estatal no nome e **nenhuma** das licitações de folha era de estatal.

A explicação mais provável não é furo de coleta: a folha de uma estatal é contratada como serviço bancário pelo regime próprio, e não como cessão onerosa de um direito público. A detecção foi por padrão no nome do órgão — uma estatal com nome atípico escaparia —, então o zero basta para não tratar estatais como lacuna prioritária, mas não para afirmar que elas nunca licitam folha. O campo de esfera do PNCP distingue município de estado, não estatal de administração direta.

## Relacionadas

[[MOC Legal]] · [[Lei 14.133-2021 - visão geral]] · [[Garantia contratual]] · [[ADR-001 Escopo somente setor público]] · [[Fontes de dados — PNCP]]
