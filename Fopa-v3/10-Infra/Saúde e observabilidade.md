---
tipo: componente
familia: infra
status: verificado
atualizado: 2026-09-29
fonte_codigo:
  - api/worker.py
  - api/site.py
  - n8n/workflows/W00.json
  - n8n/workflows/W40.json
  - n8n/workflows/W90.json
  - db/007_execucoes_workflow_buscas_termos_orcamento.sql
  - db/008_emails_usuarios_sessoes_jobs_saude.sql
tags: [infra, observabilidade, saude, monitoramento]
---

# Saúde e observabilidade

> [!abstract] Em uma frase
> O sistema responde a três perguntas o tempo todo — **está de pé?** (os healthchecks dos containers e o `/api/saude`), **é o mesmo que foi medido?** (o contrato do worker, conferido de hora em hora) e **o que aconteceu?** (cada rodada de fluxo registrada com contadores, custo, erro e se foi cega, e cada licitação com a linha do tempo dos estados) —, tudo visível no site para os administradores.

## Papel na solução

Uma automação que roda sozinha de madrugada precisa dizer o que fez e o que não conseguiu fazer. A observabilidade aqui é desenhada para não ter silêncio ambíguo: "nada a fazer" é diferente de "não consegui olhar", "sem custo" é diferente de "custo desconhecido", "aprovado" é diferente de "regra não aplicada" ([[Consciência operacional]]).

## As três camadas

### 1. Está de pé?

| Verificação | Frequência | Efeito |
|---|---|---|
| healthcheck do Postgres (`pg_isready`) | 5 s | os outros serviços só sobem com o banco saudável |
| healthcheck do worker (`GET /health`) | 30 s | 503 se o OCR sair do contrato → container **não saudável** |
| healthcheck da API (`GET /api/saude`) | 30 s | 503 se o Postgres ou o worker caem |
| [[Página Saúde]] | a cada 30 s, no navegador | API, worker (com a versão do OCR), Postgres, n8n, última coleta e último alerta |

O `/api/saude` sem sessão devolve só o resumo (serve ao healthcheck); com sessão de administrador, o completo.

### 2. É o que foi medido?

O [[W00 Saúde]], de hora em hora, confere o **contrato do worker** e grava uma linha em `saude`:

| Item do contrato | Esperado |
|---|---|
| Tesseract | 5.4.0, com o idioma `por` |
| modelo de idioma do OCR | o mesmo SHA-256 fixado no build |
| chave do modelo no worker | **ausente** |
| código | o SHA do commit da imagem |
| armazenamento | o bucket respondendo |
| versões | das regras, do prompt e do escopo |

Em 30/09/2026: worker no SHA `ab55f759efcc…`, Tesseract 5.4.0 com `por`, armazenamento S3 `fopa-editais-1` em sa-east-1 ok, chave do modelo ausente, regras `b32b66ede7f6…`, prompt `f224a746b51a…`, escopo `5700476d5b8c…`.

### 3. O que aconteceu?

| Registro | O que guarda | Onde ver |
|---|---|---|
| `execucoes_workflow` | cada rodada de fluxo: gatilho, duração, contadores, custo, **se foi cega**, status, erro | [[Página Execuções]] |
| `licitacao_eventos` | cada mudança de estado de cada licitação, com motivo | a linha do tempo no [[Página Detalhe da licitação|detalhe]] |
| `buscas`, `buscas_paginas` | cada página e cada termo da busca, com a cobertura | Execuções |
| `chamadas_modelo` | cada chamada ao modelo, com tokens, custo e a resposta inteira | o detalhe; o custo no Painel |
| `emails` | a fila, com status e erro | [[Página E-mails]] |
| `jobs` | os jobs do worker, com progresso | Execuções |
| execuções do n8n | o nó a nó de cada execução, guardado por 720 horas | o editor do n8n (os e-mails e o site guardam os links) |

- **Erro não tratado** num fluxo raiz aciona o [[W90 Erro]], que devolve a licitação à fila, registra o estado de erro e fecha a execução — nada fica "em curso" para sempre.
- **O alerta diário** ([[W40 Alerta diário]]) calcula às 07:00 as seis prioridades do dia — sessão em até 7 dias (P1, com as que ainda não têm o valor mínimo aprovado), retificações (P2), novas (P3), revisão humana (P5), olho humano (P6) — mais as candidatas do Jev, e registra os números na execução; em 28/09/2026: "23 p1 · 5 p2 · 146 p6 · 5 p3 novas · 3.334 p5 respostas · 2 p3 publicadas · 626 p5 licitações · 1 jev candidatas · 5 p1 sem valor mínimo".
- **Custo** tem o próprio registro, conferido com a fatura ([[Custo por edital]]).

## Relacionadas

[[MOC Infra]] · [[W00 Saúde]] · [[W90 Erro]] · [[W40 Alerta diário]] · [[Página Saúde]] · [[Página Execuções]] · [[Consciência operacional]] · [[Containers e serviços]]
