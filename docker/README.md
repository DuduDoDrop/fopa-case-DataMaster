# docker/ — a stack local da FOPA v3

Compose `name: fopa` com cinco serviços (plano v3, seção 4):

| serviço | imagem | porta no host | o que é |
|---|---|---|---|
| `fopa-postgres` | `postgres:16-alpine` | `127.0.0.1:5433` | um container, dois bancos: `fopa` (negócio) e `n8n` (metadados do n8n) |
| `fopa-n8n` | `n8nio/n8n:2.37.10` | `127.0.0.1:5679` | os fluxos W00–W90 (sobe na F4) |
| `fopa-worker` | `fopa/worker:v3` (build) | nenhuma | FastAPI: OCR (Tesseract **5.4.0** compilado), BM25, prompt, verificador, render |
| `fopa-api` | `fopa/worker:v3` | `127.0.0.1:8080` | FastAPI do site: login Google, leitura do Postgres, PDFs/HTML, React |
| `fopa-migrate` | `fopa/worker:v3` | — | `python db/migrar.py`; só no profile `migrate` |

Tudo publicado **só em 127.0.0.1**. O worker não publica porta: quem fala com
ele é o n8n e a api, pela rede do compose, com Bearer `FOPA_WORKER_TOKEN`.

## O que NÃO conflita com outra stack n8n na mesma máquina

Outra stack n8n da máquina de desenvolvimento continua
intocada: ela usa a porta **5678**, os volumes `n8n_data`, `n8n_files`,
`n8n_postgres_data` e o projeto `docker`. A FOPA usa:

- projeto `fopa` (nomes de container `fopa-*`, rede `fopa_default`);
- porta **5679** para o n8n e **5433** para o Postgres — a **5432** do host é
  do PostgreSQL 17 nativo, e o Postgres da outra stack nem publica porta;
- volumes `fopa_postgres_data`, `fopa_n8n_data`, `fopa_dados`;
- `N8N_ENCRYPTION_KEY` própria (as duas instâncias nunca compartilham
  credenciais nem banco).

`docker ps` deve mostrar `n8n` e `n8n-postgres` (deles) ao lado de `fopa-*`
(nossos), cada um na sua porta.

## Como subir

```bash
cd docker
cp .env.exemplo .env          # e preencha (segredos: python -c "import secrets; print(secrets.token_hex(24))")

# 1. imagem (worker + api + site): compila leptonica 1.84.1 + Tesseract 5.4.0
#    (10-20 min na primeira vez; as camadas ficam em cache) e constrói o React
#    num stage node:22-alpine (npm ci + npm test + build; só o dist/ entra).
#    Construir do COMMIT, não da pasta: o que não está commitado não entra.
cd .. && git archive --format=tar HEAD | docker build -t fopa/worker:v3 \
    --build-arg FOPA_GIT_SHA=$(git rev-parse HEAD) -f docker/worker.Dockerfile - && cd docker

# 2. banco, worker e api
docker compose up -d fopa-postgres fopa-worker fopa-api

# 3. migração (tabelas, funções, views, papéis n8n_rw/worker_rw/api_ro/api_rw com
#    as senhas do .env). Idempotente: rodar de novo pula o que já foi aplicado.
docker compose --profile migrate run --rm fopa-migrate

# 4. acervo da v2 para o banco (lê acervo/ e amostras/ só leitura; sem API paga)
docker compose --profile importar run --rm fopa-importar
docker compose --profile importar run --rm fopa-importar python -m migracao.publicar

# 5. n8n: sobe, cria owner/chave/credenciais (worker, site, postgres, smtp se
#    houver SMTP_HOST, jev se houver JEV_API_KEY) e importa os fluxos
docker compose up -d fopa-n8n
cd .. && python n8n/bootstrap.py && python n8n/importar.py && cd docker

# 6. a regra de escopo de HOJE sobre o que o acervo trouxe com a regra antiga
#    (db/019; custo 0): tira da fila o que não é compra de folha (ADR-015)
docker compose exec fopa-worker python -c "import json,os,urllib.request as u; \
  r=u.Request('http://127.0.0.1:8000/escopo/reavaliar', data=b'{}', headers={'Authorization': \
  'Bearer '+os.environ['FOPA_WORKER_TOKEN'], 'Content-Type': 'application/json'}); \
  print(json.load(u.urlopen(r, timeout=300))['resultado'])"
```

O site fica em `http://127.0.0.1:8080` (login Google: `GOOGLE_CLIENT_ID`,
`GOOGLE_CLIENT_SECRET` e o e-mail em `usuarios`). Para a demo sem rede,
`FOPA_ENV=demo` + `FOPA_AUTH_MODE=local` libera o `/login` local — nunca em
`dev`/`prod`. Backup: `python docker/backup.py` (dumps + export cifrado do
n8n; `--verificar` restaura num Postgres efêmero). Roteiro da demo:
`docs/DEMO.md`.

`build.log` está no `.gitignore`. O `.env` também (`.env` e `.env.*` da raiz);
o compose passa cada variável por **nome** ao serviço que precisa — não há
`env_file:` em serviço nenhum, e nenhum serviço recebe `ANTHROPIC_API_KEY`
(ela vive só na Credential do n8n).

### Ordem importa na primeira subida

O banco `n8n` e o usuário `n8n` nascem no **init** do Postgres
(`postgres/init/01_bancos.sql`), que só roda com o volume vazio. Se a primeira
subida falhar (por exemplo `N8N_DB_PASSWORD` vazia), o volume já foi
inicializado e o init não roda de novo: `docker compose down -v` (apaga os
volumes — só numa stack recém-criada) e subir outra vez.

## O que o build garante e o que ele só mede

**Falha o build** (portões):

- `tesseract --version` ≠ `5.4.0`;
- `tesseract --list-langs` sem `por`;
- sha256 diferente do pinado em qualquer download (tarball da leptonica, do
  Tesseract, `por.traineddata` do commit `923915d4…` do `tessdata_fast`);
- `fopa.ocr.checar_ambiente()` sem `por` — pelo caminho de código que o
  `/health` usa, não só pelo binário;
- biblioteca de runtime faltando (`ldd tesseract` com `not found`).

**Só mede e registra** (nunca falha): a equivalência de OCR com o host das
medições, sobre as 6 páginas de `tests/ocr_baseline/`. O resultado fica em
`/app/docs/ocr-equivalencia-imagem.json` dentro da imagem; copie para o repo
com o sha da imagem no nome:

```bash
sha=$(docker inspect --format '{{.Id}}' fopa/worker:v3 | cut -c8-19)
docker cp fopa-worker:/app/docs/ocr-equivalencia-imagem.json ../docs/ocr-equivalencia-$sha.json
```

Se der menos de 6/6 idênticas, vale a decisão da ADR-008 documentada em
`tests/ocr_baseline/README.md`: **a imagem é a referência**.

**Resultado medido em 24/09/2026** (`docs/ocr-equivalencia-d0db4059f800.json`,
Tesseract 5.4.0 gcc/Linux × host 5.4.0.20240606 MSVC/AVX512, mesmo
`por.traineddata`): **0/6 idênticas, similaridade mínima 0,9922**. A hipótese
"mesma minor, mesmo texto" NÃO se confirmou — mas a diferença é pequena e
localizada: em p01/p04/p05/p06 muda só o rodapé carimbado (lixo de OCR nas
duas); em p02 e p03 (pirâmide salarial) a imagem lê o fio da tabela como `|`
onde o host lia o algarismo `1` (`R$ -1 R$ -` → `R$ -| R$ -`, o defeito de
`BACKLOG.md:427-463` que a 5.3.0 também tinha) e corrige `wwyw` → `www`, mas
em troca lê `RS` no lugar de `R$` em duas células (uma por página) — o que a
guarda numérica não pega, porque o número em si não muda. Consequência: os
números de OCR passam a ser os da
imagem (regenerar a baseline com `gerar.py` dentro dela, passo 1 do README do
baseline), e `leituras.versao_ocr` distingue leitura do host de leitura da
imagem.

## Como ver a saúde

```bash
# api: 200 com tudo de pé; 503 quando o Postgres ou o worker caem, com `caiu`
# dizendo quem (o n8n fora vai para `avisos`, não derruba o healthcheck). Em
# prod, sem sessão, o corpo diz só ok/caiu/avisos.
curl http://127.0.0.1:8080/api/saude

# worker (não publica porta: de dentro do container)
docker compose exec fopa-worker python -c "import urllib.request;print(urllib.request.urlopen('http://127.0.0.1:8000/health').read().decode())"
```

No `/health` do worker conferir: `tesseract` começa com `5.4.0`, `por` em
`idiomas`, `tessdata_sha256` = `c4932b93…`, `anthropic_key_presente` = `false`,
`git_sha` = o commit do build. O healthcheck do compose usa a mesma rota: um
worker com OCR errado responde 503 e nunca fica `healthy`.

```bash
docker inspect fopa-worker --format '{{range .Config.Env}}{{println .}}{{end}}' | grep -c ANTHROPIC   # tem de dar 0
```

## Testes

`python -m pytest docker/tests -q` valida o `docker compose config` (nome,
portas em loopback, volumes `fopa_*`, nenhuma env `ANTHROPIC*`, profile da
migração), os pinos e portões do Dockerfile e a cobertura do `.env.exemplo`.
Não sobe container; precisa do `docker compose` no PATH.

## Rodar o worker fora do compose (plano B)

Se a compilação da 5.4.0 travar nesta máquina, o worker roda no host
(`uvicorn api.worker:app --port 8000` na raiz, com o Tesseract 5.4.0 do
Windows) e o n8n o alcança por `http://host.docker.internal:8000`
(`FOPA_WORKER_URL` na Data Table). Decisão registrada no plano, seção 12.
