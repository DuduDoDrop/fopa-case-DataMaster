---
tipo: referencia
familia: reproducao
status: verificado
atualizado: 2026-09-28
fonte_codigo:
  - docker/compose.yml
  - docker/.env.exemplo
  - .env.exemplo
  - docker/worker.Dockerfile
  - docker/README.md
  - docs/DEPLOY.md
  - n8n/bootstrap.py
  - n8n/importar.py
  - n8n/executar.py
  - api/demo_reservar.py
  - db/migrar.py
tags: [reproducao, instalacao, docker, n8n, execucao]
---

# Como rodar em outra máquina

> [!abstract] Em uma frase
> Com **Docker, Git e Python**, a solução inteira sobe numa máquina nova a partir do repositório: uma imagem construída do código (com o Tesseract compilado e o site testado no *build*), um banco migrado por script, o n8n com as credenciais e os 15 fluxos importados por script — e, sem nenhuma chave paga, dá para descobrir licitações reais no PNCP, baixá-las, lê-las e ver o pipeline publicar uma extração de ensaio; com uma chave de modelo, a extração é a de produção.

## Papel na solução

Responde "como eu executo isto no meu equipamento": tudo o que é preciso para instalar, configurar e executar está versionado no repositório — `docker/` (composição e imagem), `db/` (migrações), `n8n/` (fluxos e scripts de instalação) e `ci/` (testes). Nada depende de passo manual na interface do n8n nem de arquivo que exista só na máquina de produção. Para ver a versão no ar sem instalar nada, veja [[Como acessar a versão no ar]].

## O que é preciso

| Item | Para quê | Obrigatório |
|---|---|---|
| **Docker** com **Compose v2** (Docker Desktop no Windows e no macOS) | os cinco serviços da solução | sim |
| **Git** | clonar o repositório | sim |
| **Python 3.12** | os scripts do n8n (só biblioteca padrão) e os testes | sim |
| acesso à internet | baixar as imagens base, compilar o OCR, consultar o PNCP (API pública, sem chave) | sim |
| portas livres em 127.0.0.1: **5433** (Postgres), **5679** (n8n), **8080** (site) | tudo é publicado só no *loopback* — nada aparece na rede local | sim |
| memória | a produção roda com 2 vCPU e 2 GB ([[Hospedagem na AWS]]); o que pesa é o OCR | — |
| chave da Anthropic ou da OpenAI | extração com modelo de verdade | não |
| cliente OAuth do Google | login com Google na máquina local (sem ele, há o login local de demonstração) | não |
| servidor SMTP | enviar os e-mails (sem ele, os e-mails ficam na fila com o motivo) | não |

## Dois modos de execução

| | **Modo A — demonstração sem agenda** (recomendado) | **Modo B — produto completo** |
|---|---|---|
| Fluxos publicados | só os que não têm agenda: W20, W21, W22, W23, W24 e W90 | os 15, como em produção |
| O que roda sozinho | nada: cada fluxo é disparado à mão | a agenda inteira ([[Horários e agendamentos]]) |
| Coleta no PNCP | quando você pede | todo dia útil, com o histórico de madrugada |
| E-mails | ficam na fila (o W50 não está publicado) | enviados pelo W50, se houver SMTP |
| Botões do site que chamam a automação | não (o W11 não está publicado) | sim |

Os passos 1 a 8 são os mesmos nos dois modos; muda só o passo 6.

## Passo a passo

### 1. Clonar

```bash
git clone https://github.com/DuduDoDrop/fopa-case-DataMaster.git
cd fopa-case-DataMaster
```

### 2. Configurar o ambiente (`docker/.env`)

```bash
cp docker/.env.exemplo docker/.env
python -c "import secrets; print(secrets.token_hex(24))"   # gere um valor por segredo
```

O `docker/.env.exemplo` documenta cada variável, **sem nenhum valor**. Para rodar localmente, preencha:

| Variável | Valor local |
|---|---|
| `FOPA_ENV` / `FOPA_AUTH_MODE` | `demo` / `local` — libera o login local sem Google (só é aceito com `FOPA_ENV=demo`) |
| `FOPA_N8N_PUBLIC_URL` / `FOPA_SITE_URL` | `http://localhost:5679/` / `http://localhost:8080` |
| `FOPA_WORKER_TOKEN`, `FOPA_SITE_TOKEN`, `SESSION_SECRET` | segredos gerados |
| `POSTGRES_PASSWORD`, `N8N_DB_PASSWORD`, `N8N_RW_PASSWORD`, `WORKER_RW_PASSWORD`, `API_RO_PASSWORD`, `API_RW_PASSWORD` | segredos gerados (só letras e números, porque entram em URL) |
| `N8N_ENCRYPTION_KEY` | segredo gerado — **nunca mudar depois de subir** (cifra as credenciais do n8n) |
| `GOOGLE_CLIENT_ID`, `GOOGLE_CLIENT_SECRET`, `OAUTH_REDIRECT_URI` | opcionais: para o login com Google (`http://localhost:8080/auth/google/callback`) com `FOPA_AUTH_MODE=google` |
| `SMTP_*` | opcionais: para o W50 enviar e-mails |

**A chave do modelo não vai para nenhum container.** Se houver uma, ela fica no `.env` da raiz (copiado de `.env.exemplo`: `ANTHROPIC_API_KEY`, `OPENAI_API_KEY`, `JEV_API_KEY`), que só o `n8n/bootstrap.py` lê, para criar a credencial dentro do n8n ([[Controle de acesso e segredos]]).

### 3. Construir a imagem

```bash
cd docker
FOPA_GIT_SHA=$(git rev-parse HEAD) docker compose build fopa-worker
```

No PowerShell: `$env:FOPA_GIT_SHA = git rev-parse HEAD; docker compose build fopa-worker`.

Uma única imagem serve ao worker, à API do site e à migração. Na primeira vez leva de 10 a 20 minutos: compila a **Leptonica 1.84.1** e o **Tesseract 5.4.0**, baixa o `por.traineddata` de um commit fixo e **confere o sha256 de cada download**, e constrói o site depois de rodar os testes dele. O *build* falha — em vez de instalar outra coisa em silêncio — se a versão do Tesseract, o idioma português ou qualquer sha256 não baterem ([[Containers e serviços]], [[ADR-008 OCR — stack, configuração e limites]]).

### 4. Subir o banco e migrar

```bash
docker compose up -d fopa-postgres
docker compose --profile migrate run --rm fopa-migrate
```

O Postgres nasce com dois bancos — `fopa` (o do produto) e `n8n` (o do orquestrador). A migração aplica as 51 migrações em ordem, cria os papéis `n8n_rw`, `worker_rw`, `api_ro` e `api_rw` com as senhas do `.env` e semeia a configuração (com o provedor `simulado`: nenhuma chamada paga sai sem que alguém mude isso). Ela é **idempotente** e confere o hash de cada migração já aplicada ([[Migrações do banco]]).

> [!warning] Primeira subida
> O banco `n8n` e seu usuário nascem no *init* do Postgres, que só roda com o volume vazio. Se a primeira subida falhar (por exemplo, `N8N_DB_PASSWORD` vazia), corrija o `.env`, apague os volumes dessa instalação recém-criada (`docker compose down -v`) e suba de novo.

### 5. Subir o worker, o site e o n8n

```bash
docker compose up -d fopa-worker fopa-api fopa-n8n
```

> [!note] Instância que já tinha fluxos publicados
> Numa instalação nova o banco `n8n` está vazio. Se a instância já teve fluxos com agenda publicados, despublique tudo **antes** de subir o n8n, para nada rodar sozinho: com só o `fopa-postgres` de pé, `docker exec -i fopa-postgres psql -U postgres -d n8n -c "UPDATE workflow_entity SET active = false, \"activeVersionId\" = NULL"`.

### 6. Instalar o n8n e importar os fluxos

Da raiz do repositório:

```bash
python n8n/bootstrap.py
python n8n/importar.py --publicar W20,W21,W22,W23,W24,W90   # modo A
python n8n/importar.py                                       # modo B (publica os 15)
```

- **`bootstrap.py`** cria o dono da instância (senha aleatória, gravada em `n8n/.segredos/`, fora do git), a chave da API pública do n8n e as credenciais por nome: Postgres (`n8n_rw`), worker, site e — só se o valor existir — SMTP, Jev, OpenAI e Anthropic. É idempotente e nunca imprime um segredo.
- **`importar.py`** sobe os 15 JSON de `n8n/workflows/`, resolvendo os marcadores `{{WF:W90}}` e `{{CRED:nome}}` para os ids desta instância, das folhas para a raiz (o n8n recusa publicar um fluxo que chama subfluxo não publicado). Rodar de novo não duplica nada. `--publicar` escolhe o que fica ativo; `--publicar nenhum` só carrega ([[Convenções dos fluxos n8n]]).

### 7. Conferir a saúde

```bash
curl http://127.0.0.1:8080/api/saude
docker compose exec fopa-worker python -c "import urllib.request;print(urllib.request.urlopen('http://127.0.0.1:8000/health').read().decode())"
```

No `/health` do worker: `tesseract` começando por `5.4.0`, `por` nos idiomas, `tessdata_sha256` = `c4932b93…`, `anthropic_key_presente` = `false` e o `git_sha` do commit construído. Um worker com o OCR errado responde 503 e nunca fica *healthy* ([[Saúde e observabilidade]]).

### 8. Entrar no site

Abra **http://localhost:8080/login**: no modo local de demonstração, a entrada é como o administrador semeado pela migração, com acesso a todas as páginas ([[MOC Site]]). O editor do n8n fica em **http://localhost:5679**; o e-mail e a senha do dono criado no passo 6 estão em `n8n/.segredos/owner.json`. É no editor que se vê cada fluxo nó a nó e cada execução.

### 9. Trazer licitações reais (custo zero)

```bash
python n8n/executar.py W01
```

Roda a [[W01 Descoberta]] uma vez, pelo gatilho manual: consulta o PNCP, classifica cada compra **por regra** e grava as licitações de folha no banco. Sem chave do Jev, o sinal de IA fica vazio e a rodada segue. As licitações aparecem na [[Página Painel]]; o **número de controle** de cada uma está no card e no detalhe.

### 10. Baixar e ler uma licitação (custo zero)

```bash
python n8n/executar.py W20 --itens '{"controle": "<número de controle>", "forcar": true}' --timeout 900
```

O [[W20 Processar uma licitação]] baixa todos os documentos, converte o que não é PDF, lê página a página com OCR onde precisa e congela o texto. Com o provedor `simulado`, ele **para em `preparada`**, sem chamar modelo. O `--timeout` é só quanto o script espera; a execução continua no n8n se passar disso.

### 11. Extrair

**Sem chave — ensaio do pipeline inteiro, R$ 0:**

```bash
docker exec fopa-worker python -m api.demo_reservar --reservar --controles <número de controle>
python n8n/executar.py W20 --itens '{"controle": "<número de controle>", "forcar": true}' --timeout 900
```

A licitação é marcada como **reservada** e **de ensaio**. O [[W23 Extrair]] responde com o provedor `simulado` — expressões regulares sobre o texto, no mesmo formato do modelo —, e o [[W24 Verificar e publicar]] verifica e publica. O card leva o selo **"ensaio"**: o banco só aceita resultado simulado como vigente em licitação de ensaio ([[Controles de consistência]]). Serve para ver o caminho completo — leitura, verificação, relatório, fila de revisão —; as respostas não são do modelo.

**Com chave — a extração de produção:**

1. Coloque a chave no `.env` da raiz e rode de novo `python n8n/bootstrap.py` (ele cria só a credencial que falta).
2. Na [[Página Admin]], troque o provedor para `claude` (ou `openai`); o site pede confirmação de custo.
3. Rode o W20 da licitação `preparada`, como no passo 10.

O W23 faz as 3 chamadas em lote, o reforço do [[Best-of-N]] quando alguma resposta falha e grava o custo de cada chamada; a extração custa de R$ 0,20 a cerca de R$ 5 por edital, sob o teto diário do Admin ([[Custo por edital]]).

> [!warning] Provedor pago com a agenda ligada
> No modo B, deixar o provedor global num modelo pago faz a fila da manhã extrair **tudo** o que estiver preparado, até o teto do dia. Em produção o provedor global fica `simulado`, e a extração paga acontece pelo botão **"Extrair com IA"**, que vale só para aquela licitação ([[W10 Fila]], [[Modelos e provedores]]).

### 12. Guardar e parar

Com a stack de pé, da raiz do repositório:

```bash
python docker/backup.py              # opcional: dumps dos dois bancos e export cifrado do n8n, em backups/ (fora do git)
python docker/backup.py --verificar  # restaura o mais recente num Postgres efêmero e compara as contagens
cd docker && docker compose stop     # para tudo; os dados ficam nos volumes
```

As credenciais do n8n saem cifradas com a `N8N_ENCRYPTION_KEY`, que não vai no backup. Detalhes em [[Backup e restauração]].

## Para colocar num servidor com domínio

O mesmo repositório sobe em produção com o arquivo adicional `docker/compose.prod.yml`: o Caddy com HTTPS automático na frente, o armazenamento no S3, o login só pelo Google e as URLs públicas derivadas dos domínios. O roteiro completo — servidor, DNS, bucket, `.env` de produção, imagem, credenciais do n8n, OCR na CPU nova e agenda de backup — está em `docs/DEPLOY.md` e resumido em [[Deploy e atualização]].

## Como provar que a instalação está certa

- `python ci/rodar.py --camada a` roda as suítes numa cópia limpa, com Postgres efêmero e sem chave ([[Testes e CI]]).
- `python ci/rodar.py --camada b` confere a instância local: os fluxos no n8n, os invariantes no banco e a ausência de chave nos containers.

## Relacionadas

[[MOC Reprodução]] · [[Como acessar a versão no ar]] · [[Testes e CI]] · [[Containers e serviços]] · [[Deploy e atualização]] · [[Horários e agendamentos]] · [[Controle de acesso e segredos]] · [[Arquitetura]]
