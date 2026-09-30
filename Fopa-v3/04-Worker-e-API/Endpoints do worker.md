---
tipo: referencia
familia: worker-e-api
status: verificado
atualizado: 2026-09-28
fonte_codigo:
  - api/worker.py
  - api/rotas_extracao.py
  - api/rotas_jobs.py
  - api/rotas_jev.py
  - api/rotas_escopo.py
  - api/extracao.py
tags: [worker, api, endpoints, referencia]
---

# Endpoints do worker

> [!abstract] Em uma frase
> As rotas HTTP internas do worker que o n8n chama — todas autenticadas por token Bearer, exceto o `/health` —, com o que cada uma recebe, faz e devolve, e qual fluxo a usa.

## Papel na solução

É o **contrato** entre o orquestrador e o processamento. Cada rota faz uma coisa, reaproveitando o núcleo `scripts/fopa`; nenhuma chama modelo generativo (quem chama é o [[W23 Extrair]]).

## Saúde e versões

| Método e rota | Auth | O que faz | Quem chama |
|---|---|---|---|
| `GET /health` | não | contrato de saúde: Tesseract 5.4.0 com `por`, SHA-256 do `tessdata`, `git_sha`, hashes de regras/prompt/escopo, armazenamento, `anthropic_key_presente`; 503 se o OCR estiver fora do contrato | Docker, [[W00 Saúde]], API do site |
| `GET /versao` | sim | `versao_regras`, `versao_prompt`, `escopo_versao`, `git_sha` | [[W11 Ações do site]], [[W30 Reverificar em lote]] |

## Escopo

| Rota | O que faz | Quem chama |
|---|---|---|
| `POST /escopo` | aplica a **regra de escopo** a uma lista de objetos; devolve `dentro`, `motivo` e `escopo_versao` ([[Regras antes de IA]]) | [[W01 Descoberta]], [[W11 Ações do site]] |
| `POST /escopo/reavaliar` | reaplica a regra de hoje ao que foi julgado por outra versão (`seco` só conta; `controles` restringe) e move o estado pela função do banco | operação, depois de mudar a regra |

## Jobs

| Rota | O que faz | Quem chama |
|---|---|---|
| `POST /jobs/baixar` | download, conversão, medição e armazenamento dos documentos | [[W21 Baixar]] |
| `POST /jobs/paginas` | leitura congelada com OCR | [[W22 Ler]] |
| `POST /jobs/historico` | rodada do histórico e dos contratos do PNCP | [[W41 Histórico do PNCP]] |
| `POST /jobs/importar` | importação do acervo da versão anterior | montagem |
| `GET /jobs/{id}` | status (`queued`, `running`, `done`, `error`), progresso, resultado ou erro | os fluxos acima |

## Extração e verificação

| Rota | Entrada | O que faz | Quem chama |
|---|---|---|---|
| `POST /prompt` | leitura, modalidade, lote, `k_rag`, provedor, modelo, esforço, teto de saída, `ids_pendentes` | escolhe o modo (contexto completo ou RAG por BM25), monta os lotes e devolve, para cada um, o **corpo exato** do Claude e o da OpenAI e o SHA-256 ([[Prompt do extrator]]) | [[W23 Extrair]] |
| `POST /reforco` | os mesmos parâmetros + a execução | funde e verifica o que já veio; se há perguntas que falharam e cabe rodada, devolve os lotes do **reforço** (Best-of-N); senão, `fim` ([[Best-of-N]]) | [[W23 Extrair]] |
| `POST /responder-simulado` | o corpo do lote | resposta por expressões regulares, no formato do Claude; custo zero | [[W23 Extrair]] (provedor `simulado`) |
| `POST /gravado/v1/messages?controle=` | o corpo do lote | repete a resposta real gravada daquela licitação | [[W23 Extrair]] (provedor `gravado`) |
| `POST /custo` | modelo e uso de tokens | calcula US$ e R$ pela tabela de preços; sem preço, nulo | [[W23 Extrair]] |
| `POST /verificar` | execução, modalidade, usar itens da API | funde as chamadas, escolhe entre candidatos do reforço, roda o verificador, fecha a execução e grava a verificação; 409 se já verificada nesta versão das regras ([[Verificador determinístico]]) | [[W24 Verificar e publicar]] |
| `POST /reverificar` | controle (ou execução) | regras atuais sobre as respostas vigentes e o texto congelado; grava verificação nova e o diff | [[W11 Ações do site]], [[W30 Reverificar em lote]] |
| `POST /importar-respostas` | controle, leitura, 17 respostas, procedência, `verificar` | valida as respostas e grava a execução (sem custo de API); no modo republicar, já verifica | [[W11 Ações do site]] |
| `POST /render` | verificação | gera o relatório HTML e guarda no armazenamento; devolve o `html_uri` | [[W24 Verificar e publicar]] |
| `GET /questionario` | — | as 17 perguntas, o esquema e a instrução de sistema — o contrato do prompt | API do site |

## Jev (prefixo `/jev`)

| Rota | O que faz | Quem chama |
|---|---|---|
| `POST /jev/escopo/corpos` | monta a pergunta de escopo (objeto) com o critério medido | [[W01 Descoberta]] |
| `POST /jev/escopo/edital/corpos` | monta a pergunta de escopo com o **edital** (objeto + páginas mais relevantes) | [[W22 Ler]] |
| `POST /jev/escopo/interpretar` | converte a resposta em probabilidade e grava em `sinais_jev` | [[W01 Descoberta]], [[W22 Ler]] |
| `POST /jev/sustenta/corpos` | monta "este trecho sustenta esta resposta?" para as aprovadas | [[W24 Verificar e publicar]] |
| `POST /jev/sustenta/interpretar` | grava o sinal e, havendo convicção contrária, abre a candidata na revisão | [[W24 Verificar e publicar]] |

Nenhuma rota do Jev escreve veredito, confiança ou escopo — o Jev é **sinal** ([[Jev — score de escopo e sustentação]]).

## Autenticação

Todas as rotas, exceto `/health`, exigem `Authorization: Bearer <FOPA_WORKER_TOKEN>` (credencial `worker` do n8n). Em produção o worker só é alcançável pela rede interna do Docker, por HTTPS com certificado interno ([[Domínio, DNS e HTTPS]]).

## Relacionadas

[[MOC Worker e API]] · [[Worker — visão geral e jobs]] · [[API do site — endpoints]] · [[MOC Fluxos n8n]] · [[Convenções dos fluxos n8n]]
