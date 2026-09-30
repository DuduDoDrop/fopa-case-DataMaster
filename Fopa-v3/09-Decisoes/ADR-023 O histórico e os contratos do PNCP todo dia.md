---
tipo: decisao
familia: decisoes
adr: 23
data: 2026-09-27
decisao: aceita
status: verificado
atualizado: 2026-09-28
tags: [decisao, pncp, analytics, schedule]
---

# ADR-023 — O histórico e os contratos do PNCP todo dia

> [!abstract] Em uma frase
> Todo dia às **04:30**, o [[W41 Histórico do PNCP]] recoleta do PNCP os **itens e resultados** de todo o acervo, os cabeçalhos pendentes e os **contratos assinados com os aditivos**, para que o Analytics mostre quem comprou cada folha, por quanto e até quando — sempre atualizado, sem depender de alguém rodar um script.

## Problema

O Analytics e a separação entre Painel e Histórico (o vencedor homologado manda a licitação para o histórico) dependem do que o PNCP publica depois da sessão: itens, resultados, homologação. A coleta desses dados era manual e ficava velha; e o contrato assinado com o banco — com valor e vigência de verdade —, publicado pelo PNCP, não era coletado.

## O que foi medido (27/09/2026, a partir da produção)

| Fonte | Comportamento |
|---|---|
| itens e resultados (gateway do PNCP) | ~0,1 s por chamada, sem limitação — 45 mil chamadas para ~6,6 mil licitações em 10,5 min |
| cabeçalho da compra (API de consulta) | limitou a 5 por minuto de manhã e respondeu em 1 s à tarde — **não** entra nos números financeiros |
| contratos (busca + detalhe + termos aditivos) | busca rápida; o detalhe traz o vínculo com a compra; os aditivos vêm à parte |

## Escolha

- **Um job no worker** (o coletor em Python já existia e é testado), disparado pelo W41 às 04:30 e acompanhado pelo laço de jobs longos; a rodada fica em `execucoes_workflow` com os números, ou com o motivo.
- **A rodada, idempotente:**
  1. licitação nunca coletada: a compra inteira, com o cabeçalho numa tentativa só;
  2. **o acervo inteiro:** itens e resultados de novo (o vencedor que saiu depois, o resultado cancelado);
  3. cabeçalhos pendentes com **limite de tempo** (10 minutos), nunca com meta — o que sobra fica para o dia seguinte;
  4. **contratos:** busca pelos termos ativos da descoberta, detalhe e aditivos só do contrato novo ou alterado (de todos, aos domingos); o escopo do contrato sai da **mesma regra** das licitações, porque a busca traz também software de RH e consignado.
- **Por que 04:30:** antes da descoberta (06:00) e da fila (06:00–07:50); em produção o worker tem uma vaga de job, e a rodada a ocupa por cerca de 20 minutos.
- **Termo que falha não derruba a rodada:** o que foi lido segue, e a rodada fica **cega**, como a da descoberta.

## O que a primeira rodada mostrou

22 minutos, `ok`: o acervo inteiro atualizado (6 compras tinham sumido do PNCP); **1.396 contratos** lidos sem falha, com **215 aditivos**; dos contratos, 728 de folha pela regra, 1.280 ligados a licitações do acervo, 1.231 vigentes e **220 vencendo nos 12 meses seguintes** — o sinal de quando o órgão licita de novo.

## O que custa

- ~16 mil chamadas diárias ao PNCP; o cliente tenta 3 vezes e conta a falha, sem laço.
- **Qualidade do dado do PNCP:** há compras com homologado simbólico (até R$ 1) e contrato com o valor real, e licitações cadastradas duas vezes em dias diferentes; o Analytics trata os dois casos de forma explícita e visível na tela ([[Página Analytics de Mercado]]).
- Rodar o W41 à mão dentro da janela da fila trava a vaga do worker.

## Onde vive em produção

[[W41 Histórico do PNCP]]; `api/historico_pncp.py` e `api/contratos_pncp.py`; `db/027` e `db/049`; as páginas [[Página Analytics de Mercado]] ("O que cada instituição financeira comprou", com a rodada de publicação, o preço, a data da compra e o contrato com aditivos e vigência) e [[Página Analytics Histórico FOPA]].

## O que reabriria a decisão

O PNCP passar a limitar também o gateway de itens, ou o acervo crescer a ponto de a rodada não caber antes das 06:00.

## Relacionadas

[[MOC Decisões]] · [[W41 Histórico do PNCP]] · [[Fontes de dados — PNCP]] · [[Horários e agendamentos]] · [[Página Analytics de Mercado]] · [[ADR-022 Produção na AWS, em São Paulo, numa máquina pequena]]
