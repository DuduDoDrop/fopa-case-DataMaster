---
tipo: componente
familia: worker-e-api
status: verificado
atualizado: 2026-09-28
fonte_codigo:
  - api/worker.py
  - api/jobs.py
  - api/rotas_jobs.py
  - api/__init__.py
  - docker/worker.Dockerfile
tags: [worker, jobs, nucleo, python, fastapi]
---

# Worker — visão geral e jobs

> [!abstract] Em uma frase
> O worker é um serviço Python (FastAPI) interno que **faz o trabalho pesado** da solução — baixar e converter documentos, OCR e leitura, regra de escopo, montagem do prompt, verificação sem IA, relatório HTML e a coleta do histórico do PNCP —, sempre reaproveitando o núcleo `scripts/fopa` que produziu as medições, e expondo tudo por HTTP para o n8n.

## Papel na solução

Separa **orquestração** (n8n) de **processamento** (worker). O n8n não tem Python científico nem OCR; o worker não tem agenda nem chave de modelo. Cada um faz o que faz bem ([[Arquitetura]]).

## Como é construído

| Aspecto | Detalhe |
|---|---|
| Imagem | `fopa/worker:<sha>` (a mesma imagem serve o worker e a API do site) — `docker/worker.Dockerfile` |
| OCR | Tesseract **5.4.0** e Leptonica 1.84.1 **compilados** na imagem; `por.traineddata` com SHA-256 conferido no build ([[OCR]]) |
| Conversão | LibreOffice sem tela, PyMuPDF, `bsdtar` ([[Conversão de formatos]]) |
| Núcleo | o pacote `scripts/fopa` (extrator, verificador, OCR, recuperação BM25, página, modelos) é **congelado na imagem** e importado — nunca reescrito |
| Rede | porta interna 8000, **nunca publicada**; o n8n chega por HTTPS interno (um site do Caddy só da rede do Docker) com **token Bearer** |
| Banco | papel `worker_rw` (menor privilégio) |
| Chave do modelo | **nunca** presente: o pacote é importado de um jeito que impede ler o `.env` com a chave, e o `/health` declara `anthropic_key_presente = false` |

## Jobs assíncronos

O que pode demorar vira **job**: o `POST /jobs/<tipo>` só enfileira e responde `202 {job_id}`; o n8n volta com `GET /jobs/{id}` em intervalos até o fim ([[Convenções dos fluxos n8n]]).

| Job | Quem chama | O que faz | Duração típica |
|---|---|---|---|
| `POST /jobs/baixar` | [[W21 Baixar]] | baixa os documentos ativos, converte, mede e guarda | segundos a minutos |
| `POST /jobs/paginas` | [[W22 Ler]] | leitura com OCR, varredura de texto escondido, grava `leituras` + `paginas` | até ~15 min em processos grandes com OCR |
| `POST /jobs/historico` | [[W41 Histórico do PNCP]] | a rodada diária do histórico e dos contratos | ~15 min |
| `POST /jobs/importar` | uso de montagem | importa o acervo da versão anterior a partir de um *snapshot* com manifesto | — |

**Por que job:** uma leitura com OCR levou até 183,5 s no acervo (e 881 s num processo grande); o HTTP do n8n para o worker tem tempo limite de 30 s. Esperar pela resposta derrubaria a chamada.

### O estado mora no banco
- Cada job é uma linha em `jobs` com `queued → running → done | error`, o progresso (arquivo atual, etapa) e o resultado ou o erro (tipo, mensagem, rastro).
- **Duas filas de execução:** `ocr` (a principal; concorrência `FOPA_JOBS_CONCORRENCIA`, padrão 2 — OCR é CPU e mais threads que núcleos só disputariam o processador) e `rede` (1 thread, para a rodada do histórico, que passa quase todo o tempo esperando o PNCP e não pode ocupar a vaga do OCR).
- **No arranque, todo job ativo é órfão:** o worker é um processo só; quando ele nasce, nenhum job `queued`/`running` pode ser dele — todos viram `error` ("órfão"), e o fluxo que esperava trata como falha, com backoff.
- **Erro nunca some:** exceção dentro do job vira `error` com o rastro na linha.
- Validação **antes** de enfileirar: o que dá para recusar sem trabalho (controle malformado, licitação inexistente) é recusado na hora com 422/404.

## Endpoints

A lista completa, com entrada, saída e quem chama, está em [[Endpoints do worker]].

## Relacionadas

[[MOC Worker e API]] · [[Endpoints do worker]] · [[OCR]] · [[Conversão de formatos]] · [[Containers e serviços]] · [[Convenções dos fluxos n8n]] · [[Arquitetura]]
