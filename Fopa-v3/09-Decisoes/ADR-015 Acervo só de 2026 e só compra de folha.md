---
tipo: decisao
familia: decisoes
adr: 15
data: 2026-09-24
decisao: aceita
status: verificado
atualizado: 2026-09-28
tags: [decisao, escopo, recorte, custo]
---

# ADR-015 — Acervo só de 2026 e só compra de folha

> [!abstract] Em uma frase
> O painel e a fila de extração paga cobrem **só licitações de 2026 em diante** (sessão em 2026 ou depois; sem data de sessão, publicada em 2026) e **só compra ou operação da folha pelo banco**; o resto não é apagado — fica no histórico e no Analytics, onde serve para calibrar preço.

## Problema

A fila de extração acumulava centenas de licitações quase todas encerradas, de 2022 a 2026, e parte delas nem era compra de folha (consultoria, migração de banco de dados, software, tarifas bancárias, empréstimo pessoal, conta institucional que exclui a folha). Para decidir lance, dado velho vale pouco; e o que não é compra de folha não tem lance.

## Opções

| Opção | Avaliação |
|---|---|
| processar tudo o que a busca traz | gasto em licitação encerrada e em objeto que não é folha |
| recortar só pelo ano do número de controle | o ano da compra não é o da sessão: um credenciamento de 2025 pode ter sessões até 2027 |
| **recorte pela data da sessão (ou de publicação) e escopo de compra de folha** | adotado |

## O que foi medido

- Na consulta ao PNCP, o termo principal declarava 1.895 resultados sem filtro; com `anos=2026`, 558; recebendo proposta (qualquer ano), 56. O corte na consulta tira cerca de 70% do ruído antes de qualquer processamento.
- A leitura humana de 18 objetos da fila mostrou 18 que não eram compra de folha; a regra de escopo foi apertada até recusar os 18, sem perder casos-limite legítimos (isenção de tarifas, cobrança de tarifas como serviço correlato), que viraram casos de teste.

## Escolha

- **Ano:** entra se a sessão for em 2026 ou depois; sem data de sessão, se foi publicada em 2026; sem data nenhuma, fica fora (`configuracao.ano_minimo = 2026`, mudável no Admin sem migração).
- **Objeto:** só o banco comprar ou operar a folha — cessão onerosa, venda, gestão ou processamento da folha, inclusive com arrecadação junto. Serviço que o órgão **paga** ao banco sai, salvo cessão onerosa ([[Regras antes de IA]]).
- **Na consulta:** o [[W01 Descoberta]] faz duas buscas por termo — o ano do recorte até o ano atual, e tudo que está recebendo proposta — e junta pelo número de controle.
- **No banco:** `fn_no_recorte` decide pela data; a vaga de extração (`fn_tomar_vaga_extracao`) **recusa** o que está fora do escopo ou do recorte antes de qualquer conta — é onde o dinheiro sai.

## O que custa

- Licitações antigas não são extraídas pela API; o histórico delas veio da extração por agente e do PNCP ([[ADR-014 Extração por agente, sem API]], [[ADR-023 O histórico e os contratos do PNCP todo dia]]).
- Um credenciamento antigo ainda aberto só entra se a sessão cair no recorte.

## Onde vive em produção

Painel com as ativas do recorte; Histórico com o resto (em 28/09/2026, 1.433 licitações anteriores a 2026 no histórico); `POST /escopo/reavaliar` para reaplicar a regra quando ela muda ([[Ciclo de vida de uma licitação]], [[Página Histórico]]).

## O que reabriria a decisão

Mudança de janela de interesse do banco — um ajuste de `ano_minimo`, sem migração.

## Relacionadas

[[MOC Decisões]] · [[Regras antes de IA]] · [[Escopo — o que é licitação de folha]] · [[W01 Descoberta]] · [[Funções e views do banco]] · [[ADR-003 Classificação por regras antes de IA]] · [[ADR-019 O site mostra só o que a IA confirma como folha]]
