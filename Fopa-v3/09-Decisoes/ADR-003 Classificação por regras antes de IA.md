---
tipo: decisao
familia: decisoes
adr: 3
data: 2026-09-22
decisao: aceita
status: verificado
atualizado: 2026-09-28
tags: [decisao, escopo, regras, custo]
---

# ADR-003 — Classificação por regras antes de IA

> [!abstract] Em uma frase
> Decidir se uma licitação é compra de folha é trabalho de **regras de vocabulário** — custo zero, determinístico, com motivo e versão gravados —; um modelo só opina como **segundo sinal**, e o descarte nunca acontece sem motivo auditável.

## Problema

A busca no PNCP é ruidosa: "folha de pagamento instituição financeira" declarava 1.895 resultados em 24/09/2026, cheios de software de RH, consignado e tarifa bancária. Classificar tudo com IA seria caro e não determinístico; não classificar faria cada falso positivo custar uma extração inteira.

## Opções

| Opção | Avaliação |
|---|---|
| IA para classificar tudo | caro, não determinístico, e descarte sem motivo auditável |
| Só regras, sem IA | não aponta os próprios pontos cegos |
| Classificador treinado | não há volume rotulado independente |
| **Regras primeiro, IA como sinal, humano decide a dúvida** | custo zero no caminho comum, auditável, com os pontos cegos apontados |

## O que foi medido

- Os falsos positivos iniciais ("licença de uso… software", "empréstimo pessoal consignado") caem por vocabulário negativo, sem nenhuma chamada de modelo.
- O Jev, usado como sinal sobre 1.162 licitações, apontou onde a regra errava; depois das correções, as discordâncias convictas caíram de 75 para 2 e a probabilidade média de o filtro estar certo subiu de 0,83 para 0,91 ([[Regras antes de IA]]).
- A camada de ajuste, medida antes de entrar, tirou 85 licitações sem perder nenhuma folha já publicada.

## Escolha

Regras de vocabulário decidem (`escopo.py` + a camada `escopo_ajuste.py`), gravando **motivo** e **versão**; o Jev dá a segunda opinião; o rótulo humano prevalece na tela; a extração paga só acontece para o que passou pelo portão.

## O que custa

- O vocabulário precisa de curadoria contínua — cada erro achado vira padrão com o caso real registrado no código.
- Regra rígida demais gera falso negativo silencioso — mitigado porque o Jev pontua também o que a regra recusou, e a discordância convicta vai para a fila de rótulo humano.

## Onde vive em produção

`POST /escopo` no [[W01 Descoberta]]; `POST /escopo/reavaliar` quando a regra muda; `escopo_versao` no `/health`; a aba Escopo da [[Página Revisão]]. Detalhe completo em [[Regras antes de IA]].

## O que reabriria a decisão

Um volume de rótulos humanos **independentes** do próprio filtro, grande o bastante para treinar e validar um classificador.

## Relacionadas

[[MOC Decisões]] · [[Regras antes de IA]] · [[Escopo — o que é licitação de folha]] · [[Jev — score de escopo e sustentação]] · [[ADR-015 Acervo só de 2026 e só compra de folha]]
