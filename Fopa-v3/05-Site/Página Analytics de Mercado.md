---
tipo: pagina
familia: site
rota: "/analytics"
papel_minimo: usuario
status: verificado
atualizado: 2026-09-30
fonte_codigo:
  - web/src/paginas/Analytics.tsx
  - web/src/componentes/GraficoLinhas.tsx
  - web/src/componentes/ComprasPorBanco.tsx
  - api/analytics.py
  - api/historico_pncp.py
  - api/contratos_pncp.py
tags: [site, pagina, analytics, mercado, concorrencia]
---

# Página Analytics de Mercado

> [!abstract] Em uma frase
> **Quem compra folha pública no Brasil, por quanto e quando**: o ranking das instituições financeiras que venceram licitações de folha, o valor homologado, o ticket médio, a evolução mês a mês e, para cada instituição, as compras uma a uma com o contrato e a vigência — tudo direto da API do PNCP, sem modelo.

## Papel na solução

Transforma o sistema de "economia de leitura" em **vantagem competitiva**: mostra onde a concorrência está comprando, a que preço e até quando cada contrato prende a folha àquele banco — informação que o fornecedor terceirizado não entrega ([[Proposta de valor]], [[Concorrência e mercado]]).

![[site-analytics-mercado.jpg]]

## O que a página mostra

### Números do mercado (em produção, coleta de 28/09/2026 04:40)

| Quadro | Valor |
|---|---|
| licitações no histórico | **2.071** |
| compradas (com vencedor) | **726** |
| valor homologado | **R$ 5,56 bi** |
| instituições compradoras | **79** |
| desertas ou fracassadas | **284** |

### "Instituições financeiras compradoras"

Tabela com, para cada instituição: licitações compradas (com barra), valor total, **ticket médio**, participação e o período (primeira e última compra). Em produção, 28/09/2026:

| Instituição | Compradas | Valor total | Ticket médio | Participação |
|---|---|---|---|---|
| Caixa Econômica Federal | 224 | R$ 838,75 mi | R$ 3,74 mi | 30,6% |
| Banco Bradesco | 195 | R$ 1,24 bi | R$ 6,36 mi | 26,6% |
| Banco Santander (Brasil) | 68 | R$ 596,79 mi | R$ 8,78 mi | 9,3% |
| Itaú Unibanco | 48 | R$ 334,83 mi | R$ 6,98 mi | 6,5% |
| Banco do Brasil | 35 | R$ 1,11 bi | R$ 31,79 mi | 4,8% |
| Banrisul | 15 | R$ 1,25 bi | R$ 83,35 mi | 2,0% |

O ranking lista **só instituições financeiras**; os demais fornecedores que venceram algum item ficam num "ver mais".

### "Compras por mês e por instituição"

![[site-analytics-grafico.jpg]]

- Gráfico de linhas, um banco por cor, por **número de licitações** ou por **valor homologado**.
- Passar o mouse (ou o dedo, ou as setas do teclado) mostra o mês inteiro; clicar num banco na legenda esconde ou mostra a linha e o eixo se reajusta.
- O mês corrente aparece **tracejado** (ainda incompleto).

### "O que cada instituição financeira comprou"

Dois filtros na mesma linha e na mesma altura, cada um com o rótulo ao lado: a **busca pelo nome da instituição** (a lista sugere as que já compraram folha) e o **período da compra**, que olha a data da compra, não a da publicação; no celular, um filtro por linha. A tabela mostra, compra a compra: a licitação, a **rodada** de publicação (primeira, segunda…), o **preço**, a data e o **contrato**, com a **vigência** — até quando aquela folha fica com aquele banco.

### Filtros

- **Período:** Todo o histórico · 2026 · 2025 · 2024 · 2023 · 2022 · Escolher datas.
- **Mostrar fora do escopo:** inclui o que a regra e a IA tiraram do escopo de folha (para auditoria).

## Regras de cálculo

| Regra | Por quê |
|---|---|
| A instituição é o **CNPJ-raiz** (8 primeiros dígitos) | as filiais de um banco são o mesmo comprador |
| Resultado com homologação cancelada **não** conta | não houve compra |
| **Compra cadastrada duas vezes** no PNCP (mesmo órgão, mesmo vencedor, mesmo valor ±1%, publicações a até 7 dias ou homologação no mesmo dia) conta **uma** vez | evita dobrar a soma do banco (29 casos em produção) |
| **Homologado simbólico** (até R$ 1,00) com contrato de milhões: vale o **valor do contrato** | o PNCP traz compras homologadas por R$ 0,01 com contrato de R$ 5,5 mi (7 casos em produção) |
| Datas absurdas do PNCP (ano 255, 1858) são descartadas do gráfico | uma data digitada errada esticava o eixo a milhares de meses |

## De onde vêm os dados

| Parte | Rota da API | Fonte |
|---|---|---|
| números, ranking, gráfico | `GET /api/analytics?…` | `pncp_compras`, `pncp_itens`, `pncp_resultados`, `pncp_contratos` |
| compras de uma instituição | `GET /api/analytics/compras?…` | `pncp_resultados` + `pncp_contratos` + `pncp_contrato_termos` |

Tudo coletado todo dia às 04:30 pelo [[W41 Histórico do PNCP]]. Com o PNCP fora do ar, a página continua mostrando a última coleta boa: uma falha nunca apaga o que já foi coletado (correção de 30/09/2026).

## Quem vê

Todo usuário logado.

## Relacionadas

[[MOC Site]] · [[Página Analytics Histórico FOPA]] · [[W41 Histórico do PNCP]] · [[Fontes de dados — PNCP]] · [[Concorrência e mercado]] · [[ADR-023 O histórico e os contratos do PNCP todo dia]]
