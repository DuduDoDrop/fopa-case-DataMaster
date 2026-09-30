---
tipo: decisao
familia: decisoes
adr: 18
data: 2026-09-25
decisao: aceita
status: verificado
atualizado: 2026-09-28
tags: [decisao, download, coleta]
---

# ADR-018 — Licitação de folha pega todos os arquivos

> [!abstract] Em uma frase
> Os tetos de segurança do download — 120 MB por arquivo, 400 MB por licitação e 600 páginas por arquivo — **não valem para licitação confirmada como folha**: nela, todos os documentos disponíveis são baixados e lidos, porque a resposta pode estar justamente no anexo grande.

## Problema

Os tetos existiam contra arquivo mal formado ou hostil, com folga de quatro vezes o maior caso observado. Mas uma licitação de folha (Maringá/PR) tinha o processo administrativo inteiro num PDF de **773 páginas**: o arquivo foi recusado pelo teto de 600, a extração só viu 13 páginas de avisos e respondeu **5 de 17**. As extrações publicadas com algum arquivo bloqueado respondiam, em média, 11,2 perguntas; as outras, 12,5.

## Opções

| Opção | Avaliação |
|---|---|
| manter os tetos para todos | perde o documento que responde |
| tirar os tetos de todos | expõe o pipeline a arquivo hostil fora do escopo |
| **sem teto para licitação de folha; tetos para o resto** | adotado |

## Escolha

- "Confirmada como folha" = o **escopo efetivo** (a regra, com o rótulo humano prevalecendo) — o mesmo que o site e a fila usam. O worker pergunta ao banco antes de baixar e, se for folha, **nenhum dos três tetos recusa documento**.
- Os tetos continuam valendo para o que não é folha.

## O que foi medido

As licitações publicadas que tinham perdido arquivo foram baixadas de novo: **59 de 59** leram tudo. Maringá passou de 13 para **786 páginas** lidas (773 do processo, com texto nativo, em 289 s).

## O que custa

Documento grande demora mais para ler, sobretudo se for escaneado (um job de OCR por vez em produção); se o job passar da espera do [[W22 Ler]], a licitação vai para `erro_leitura` e a nova tentativa reaproveita a leitura que terminar.

## Onde vive em produção

`api/baixar.py` (a pergunta ao banco e a dispensa dos tetos), chamado pelo [[W21 Baixar]].

## O que reabriria a decisão

Um documento de folha que, sem teto, comprometa a operação (memória ou tempo) — o caminho seria fatiar a leitura, não recusar o documento.

## Relacionadas

[[MOC Decisões]] · [[W21 Baixar]] · [[ADR-017 O arquivo que não é PDF vira PDF]] · [[Escalabilidade]]
