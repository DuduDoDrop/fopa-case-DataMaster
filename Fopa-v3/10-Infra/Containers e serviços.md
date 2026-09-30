---
tipo: componente
familia: infra
status: verificado
atualizado: 2026-09-28
fonte_codigo:
  - docker/compose.yml
  - docker/compose.prod.yml
  - docker/worker.Dockerfile
  - docker/Caddyfile.exemplo
  - docker/postgres/init
tags: [infra, docker, containers, compose]
---

# Containers e serviços

> [!abstract] Em uma frase
> A solução roda em **Docker Compose** (projeto `fopa`): um Postgres com dois bancos, o n8n, o worker e a API do site — **a mesma imagem** com processos diferentes —, o Caddy na frente com HTTPS e dois serviços de uso pontual (migração e importação); em produção, **só o Caddy tem porta pública**.

## Papel na solução

A composição é a unidade de implantação: o mesmo arquivo sobe a infraestrutura de desenvolvimento e, com um arquivo de sobreposição, a produção. Tudo vem de variáveis de ambiente passadas **por nome** a cada serviço (nunca um arquivo de ambiente inteiro despejado num container), e nenhum serviço recebe a chave de API do modelo.

## Os serviços

| Serviço | Imagem | O que faz | Porta | Volumes |
|---|---|---|---|---|
| `fopa-postgres` | `postgres:16-alpine` | dois bancos: `fopa` (negócio) e `n8n` (metadados do n8n: fluxos, execuções, credenciais cifradas) | nenhuma em produção (backup e restauração por `docker exec`); `127.0.0.1:5433` no desenvolvimento | `fopa_postgres_data` |
| `fopa-n8n` | `n8nio/n8n:2.37.10` | os 15 fluxos; fuso `America/Sao_Paulo`; execuções guardadas por 720 horas; nós de executar comando e de ler disco **excluídos** | `127.0.0.1:5679` (o editor só por túnel; o público passa pelo Caddy) | `fopa_n8n_data` |
| `fopa-worker` | `fopa/worker:<sha do commit>` | o processamento: download e conversão, OCR, prompt, verificação, relatório, histórico, jobs longos | nenhuma — só na rede interna, por HTTPS e token | `fopa_dados` (no desenvolvimento; em produção os arquivos vão ao S3) |
| `fopa-api` | **a mesma imagem**, outro comando (`uvicorn api.site:app`) | o site React e a API do site; lê o banco como `api_rw`, o armazenamento só para leitura | `127.0.0.1:8080` (diagnóstico); o público passa pelo Caddy | `fopa_dados` só leitura |
| `fopa-caddy` | `caddy:2.11.4-alpine` | HTTPS com certificado automático para o site e o n8n; o endereço interno HTTPS do worker | **80 e 443** (TCP e UDP para HTTP/3) — as únicas públicas | `fopa_caddy_data` (certificados), `fopa_caddy_config` |
| `fopa-migrate` | a imagem do worker | aplica as migrações do banco; só sob demanda (perfil `migrate`), nunca num `up` | — | — |
| `fopa-importar` | a imagem do worker | importou o acervo anterior; só sob demanda (perfil `importar`), com o acervo montado só para leitura | — | `fopa_dados` |

## A imagem do worker (`docker/worker.Dockerfile`)

Construída em três estágios, com **versão e SHA-256 fixos** para tudo o que é baixado:

1. **OCR:** compila a Leptonica 1.84.1 e o **Tesseract 5.4.0** a partir das fontes, conferindo o hash de cada pacote e a versão do binário.
2. **Site:** instala as dependências do front (`npm ci`), **roda os testes do front** e gera o build do React — um teste que falha impede a imagem.
3. **Imagem final** (`python:3.12-slim-bookworm`): o Tesseract e a Leptonica do primeiro estágio; o modelo de português do Tesseract fixado por commit e SHA-256; LibreOffice sem tela (texto e planilha), fontes com as métricas das do Office e o `bsdtar` para RAR ([[Conversão de formatos]]); o código Python; o SHA do commit gravado na imagem (`FOPA_GIT_SHA`), que o `/health` informa.

Na última etapa, a imagem confere que o Tesseract responde a versão certa e tem o idioma `por` — senão o build falha.

## Saúde dos containers

| Serviço | Verificação | Efeito |
|---|---|---|
| `fopa-postgres` | `pg_isready` a cada 5 s | os outros só sobem com o banco saudável |
| `fopa-worker` | `GET /health` a cada 30 s | responde 503 se o OCR estiver fora do contrato (versão, idioma, hash do modelo) — o container fica **não saudável** e o [[W00 Saúde]] alerta |
| `fopa-api` | `GET /api/saude` a cada 30 s | 503 se o Postgres ou o worker caem |

Todos com `restart: unless-stopped`.

## Desenvolvimento × produção

| Item | Desenvolvimento (`compose.yml`) | Produção (`+ compose.prod.yml`) |
|---|---|---|
| portas | tudo em `127.0.0.1` | só o Caddy público; Postgres sem porta |
| HTTPS | não | Caddy com Let's Encrypt; `N8N_SECURE_COOKIE` e cookie de sessão `Secure` |
| login | Google ou login local de demonstração | **só Google** (`FOPA_AUTH_MODE=google` fixo) |
| armazenamento | disco (`fs`) | **S3** (`STORAGE_BACKEND=s3`) no worker e na API |
| n8n → worker | HTTP interno | **HTTPS interno** (`https://fopa-worker-tls:8443`, site do Caddy não publicado, certificado próprio em que o n8n confia) + o mesmo token |
| imagem | `fopa/worker:v3` | `fopa/worker:<sha curto do commit>` — voltar de versão é voltar a tag |
| obrigatórias | as senhas | + domínios, Google, S3 e segredo da sessão: sem elas, a composição **recusa subir** em vez de subir um site que falha no primeiro clique |
| concorrência de jobs | 2 | **1** (`FOPA_JOBS_CONCORRENCIA=1`) |

## Relacionadas

[[MOC Infra]] · [[Arquitetura]] · [[Hospedagem na AWS]] · [[Domínio, DNS e HTTPS]] · [[Deploy e atualização]] · [[Worker — visão geral e jobs]] · [[Saúde e observabilidade]] · [[Controle de acesso e segredos]]
