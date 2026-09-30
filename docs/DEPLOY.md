# Deploy da FOPA v3 numa VPS (F8)

O mesmo `docker/compose.yml` do dev, mais o override `docker/compose.prod.yml`:
Caddy com TLS automático na frente do site e do n8n, PDFs e RELATORIOs num
bucket S3 (R2), login Google no domínio público. É o checklist da F8
(`Fopa-v2/11-Produto-v3/Checklist F8 Nuvem.md`) escrito como passos, na ordem
em que se executam — "cloud depois" não é só configuração (plano, seção 12).

**[REQUER APROVAÇÃO]** indica as etapas que dependem de decisão, contratação ou investimento do gestor do
projeto. Nenhuma etapa deste roteiro cria conta, contrata serviço ou publica recursos de forma automática.

Convenções: comandos da VPS rodam como o usuário `fopa` em
`/srv/projeto-fopa`; `<site>` e `<n8n>` são os dois hosts públicos (ex.:
`fopa.exemplo.com.br` e `n8n.fopa.exemplo.com.br`); `<bucket>` é o bucket.

---

## 0. Decisões prévias do gestor do projeto

| # | Decisão | Opções (custo estimado, confira no dia) | Sugestão |
|---|---|---|---|
| D1 | **[REQUER APROVAÇÃO] Provedor e região da VPS** | Hetzner CPX31/CX32 (~€ 8-15/mês, Europa); DigitalOcean/Vultr (US$ 24-48/mês; Vultr tem São Paulo); AWS Lightsail ou Magalu Cloud em São Paulo (dados no Brasil) | 4 vCPU, 8 GB RAM, 80 GB SSD, Ubuntu 24.04 LTS, IPv4. OCR + até 4 extrações + n8n + Postgres não cabem bem em 4 GB |
| D2 | **[REQUER APROVAÇÃO] Bucket S3** | Cloudflare R2 (10 GB grátis, sem custo de saída; hoje são 3,4 GB e ~2.600 objetos); Backblaze B2; MinIO na própria VPS (não tira os dados do disco da VPS) | R2, bucket privado, sem domínio público |
| D3 | **[REQUER APROVAÇÃO] LGPD: onde os editais ficam** | Edital traz nome e salário de servidor. R2 não tem região no Brasil (tem jurisdição UE); VPS em São Paulo mantém o banco no Brasil | Registrar a escolha na nota "Privacidade e LGPD" do vault |
| D4 | **[REQUER APROVAÇÃO] Domínio** | Registrar um `.com.br` no Registro.br (~R$ 40/ano) ou usar subdomínios de um domínio que já existe | Dois hosts: `<site>` e `<n8n>` |
| D5 | **[REQUER APROVAÇÃO] Cloudflare na frente?** | DNS "cinza" (só DNS, o Caddy faz o TLS) ou "laranja" (proxy: corta requisição em 100 s, esconde o IP). Cloudflare Access no `<n8n>` substituiria o basic auth | Cinza. O basic auth do Caddy já protege o `/` do n8n |
| D6 | **[REQUER APROVAÇÃO] De onde vêm os dados** | **A**: levar o estado local (dump do banco + `rclone sync` do volume); **B**: do zero pelo acervo (migrar + importar na VPS) | **A**, se o banco local tem revisões, rótulos, usuários ou execuções que importam; B só se o local for descartável |
| D7 | **[REQUER APROVAÇÃO] Consent screen do Google** | "Testing" (só os e-mails cadastrados como usuários de teste entram, até 100) ou "In production" (escopos `openid email profile` não exigem verificação) | Cliente OAuth **separado** para produção |
| D8 | **[REQUER APROVAÇÃO] E-mail de produção** | Gmail com senha de app (SMTP 587) ou um provedor transacional | Muitas VPS bloqueiam a saída na porta 25 (e a Hetzner, na 465, para conta nova): use 587 |
| D9 | **[REQUER APROVAÇÃO] Backup fora da VPS** | Um 2º bucket (outra credencial, sem permissão de apagar), outro provedor ou a máquina local | Sem cópia fora da VPS, perder a VPS é perder o banco |
| D10 | **[REQUER APROVAÇÃO] Gasto de produção** | Já decidido: `provedor=claude`, automático, sem teto (~R$ 3-4 por edital). O que resta decidir é **quando** trocar o provedor (passo 13) e se liga `teto_brl_dia` | Trocar só depois do passo 12 (OCR) e do passo 13 (provas) |
| D11 | **[REQUER APROVAÇÃO] MCP do n8n de fora da VPS** | Túnel SSH (padrão; nada novo exposto) ou abrir `/mcp-server/*` no Caddy protegido só pelo token do MCP (o basic auth usa o mesmo cabeçalho `Authorization` e não convive com ele) | Túnel SSH |
| D12 | **[REQUER APROVAÇÃO] Ligar a esteira** | Desde 24/09 os fluxos saem do repositório com a esteira **desligada**: a agenda "A cada 10 min" do W10 e o nó "W10 Fila (sem esperar)" do W01 vêm com `disabled: true`. Desligada, a nuvem descobre licitação nova e não processa nenhuma; ligada, cada rodada leva até 4 ao W20 com o provedor vigente | Ligar no passo 13, junto com o D10 e depois das provas — e nunca em duas stacks ao mesmo tempo (ver o aviso do 8A) |

---

## 1. Na máquina local, antes de tudo

1. Tudo commitado: a imagem é construída **do commit** (`git archive`), nunca
   da pasta. `python -m pytest api/tests -q` verde.
2. Guardar num cofre (gerenciador de senhas), fora do repositório:
   - a `N8N_ENCRYPTION_KEY` do `docker/.env` local, se for o caminho A (sem ela
     as credenciais do n8n restauradas não abrem);
   - a pasta `n8n/.segredos/` (owner, chave da API do n8n), também no caminho A.
3. Nunca copiar o `.env` local para a VPS nem para imagem/fluxo: a VPS tem o
   dela, com segredos novos (passo 5).

## 2. VPS do zero

**[REQUER APROVAÇÃO]** D1. Criar a VPS com chave SSH (sem senha), Ubuntu 24.04.

```bash
# como root, uma vez
adduser --disabled-password --gecos "" fopa && usermod -aG sudo fopa
mkdir -p /home/fopa/.ssh && cp ~/.ssh/authorized_keys /home/fopa/.ssh/ && chown -R fopa: /home/fopa/.ssh
sed -i 's/^#\?PasswordAuthentication.*/PasswordAuthentication no/; s/^#\?PermitRootLogin.*/PermitRootLogin no/' /etc/ssh/sshd_config
systemctl restart ssh
apt-get update && apt-get -y upgrade && apt-get -y install unattended-upgrades ufw git python3 openssl
ufw allow 22/tcp && ufw allow 80/tcp && ufw allow 443/tcp && ufw allow 443/udp && ufw --force enable

# Docker Engine + plugin compose, do repositório oficial da Docker
curl -fsSL https://get.docker.com | sh
usermod -aG docker fopa
timedatectl set-timezone America/Sao_Paulo
```

> **Docker ignora o ufw** para porta publicada. É por isso que no
> `compose.prod.yml` só o Caddy publica porta pública (80/443); n8n (5679) e
> api (8080) ficam em `127.0.0.1`, e Postgres e worker não publicam nada.

```bash
# como fopa: o repositório (privado) com deploy key só leitura
sudo mkdir -p /srv/projeto-fopa && sudo chown fopa: /srv/projeto-fopa
git clone <url-do-repo> /srv/projeto-fopa && cd /srv/projeto-fopa && git checkout v3
```

## 3. DNS

**[REQUER APROVAÇÃO]** D4/D5. No DNS do domínio, registros `A` (e `AAAA`, se a
VPS tiver IPv6) de `<site>` e `<n8n>` para o IP da VPS, TTL 300, "somente DNS"
se for Cloudflare. Esperar propagar **antes** do passo 9: o Let's Encrypt
valida pela porta 80, e falhas repetidas batem no limite de emissão.

```bash
dig +short <site> ; dig +short <n8n>      # os dois devolvem o IP da VPS
```

## 4. Bucket e credencial

**[REQUER APROVAÇÃO]** D2/D3. No R2: criar `<bucket>` (privado, sem domínio
público, sem CORS — o navegador chega nele por navegação, não por `fetch`) e um
token de API **Object Read & Write restrito a esse bucket**. Anotar Access Key
ID, Secret Access Key e o endpoint `https://<conta>.r2.cloudflarestorage.com`.

A credencial precisa ler, gravar e listar. O `api/storage.py` confere a
assinatura, a região e o bucket no `/health` do worker (passo 9).

## 5. `docker/.env` de produção (na VPS)

```bash
cd /srv/projeto-fopa/docker
cp .env.exemplo .env && chmod 600 .env
python3 -c "import secrets; print(secrets.token_hex(24))"     # um por segredo
```

Preencher (valores só no arquivo; nunca em comando, issue ou chat):

| Variável | Valor |
|---|---|
| `COMPOSE_FILE` | `compose.yml:compose.prod.yml` — todo `docker compose` já inclui o override |
| `FOPA_ENV` / `FOPA_AUTH_MODE` | `prod` / `google` (o override fixa os dois nos containers de qualquer forma) |
| `FOPA_DOMINIO_SITE`, `FOPA_DOMINIO_N8N` | `<site>`, `<n8n>` — só o host |
| `FOPA_SITE_URL`, `FOPA_N8N_PUBLIC_URL` | `https://<site>` e `https://<n8n>/` (com a barra). O compose de dev exige a 2ª e os scripts do host leem as duas; nos containers, o override deriva tudo dos domínios |
| `ACME_EMAIL` | e-mail para avisos do Let's Encrypt |
| `CADDY_N8N_USUARIO` / `CADDY_N8N_HASH` | usuário do basic auth e o hash de `docker run --rm -it caddy:2.11.4-alpine caddy hash-password` **entre aspas simples** (`'$2a$14$...'`): sem as aspas o compose interpola o `$` e o hash chega vazio |
| `POSTGRES_PASSWORD`, `N8N_DB_PASSWORD`, `N8N_RW_PASSWORD`, `WORKER_RW_PASSWORD`, `API_RO_PASSWORD`, `API_RW_PASSWORD` | novos (`token_hex`), inclusive no caminho A: o dump não leva senha de papel e a migração as reaplica |
| `N8N_ENCRYPTION_KEY` | caminho **A**: a MESMA da máquina local (do cofre). Caminho B: nova. Nunca mais muda |
| `FOPA_WORKER_TOKEN`, `FOPA_SITE_TOKEN`, `SESSION_SECRET` | novos. O `bootstrap.py` (passo 10) regrava as credenciais `worker` e `site` do n8n |
| `GOOGLE_CLIENT_ID`, `GOOGLE_CLIENT_SECRET` | do cliente OAuth de produção (passo 11) |
| `S3_ENDPOINT`, `S3_BUCKET`, `S3_KEY`, `S3_SECRET`, `S3_REGION` | do passo 4; região `auto` no R2 |
| `SMTP_*` | **[REQUER APROVAÇÃO]** D8 |
| `USD_BRL` | câmbio para o custo em R$ |
| `FOPA_IMAGEM_TAG` | preenchido no passo 7 |

```bash
docker compose config --quiet && echo "compose ok"
```

> `docker compose config` **sem** `--quiet` imprime todos os segredos
> resolvidos. Na VPS, sempre com `--quiet`.

## 6. Certificado interno do worker e Caddyfile

O n8n fala com o worker por HTTPS + Bearer sem que o worker tenha porta: um
site do Caddy (`https://fopa-worker-tls:8443`) que só existe na rede do
compose. O certificado é autoassinado, válido por 10 anos, e o n8n confia nele
por `NODE_EXTRA_CA_CERTS` (o `.crt` é público; a `.key` fica só na VPS e está no
`.gitignore`).

```bash
cd /srv/projeto-fopa/docker
mkdir -p interno
openssl req -x509 -newkey rsa:2048 -nodes -days 3650 -subj "/CN=fopa-worker-tls" \
  -addext "subjectAltName=DNS:fopa-worker-tls" -keyout interno/worker.key -out interno/worker.crt
chmod 644 interno/worker.crt && chmod 600 interno/worker.key
cp Caddyfile.exemplo Caddyfile
```

Se faltar `Caddyfile` ou `interno/`, o `up` falha com o caminho (os binds têm
`create_host_path: false`). Plano B sem o certificado:
`FOPA_WORKER_URL_N8N=http://fopa-worker:8000` no `.env` (HTTP, ainda só na rede
interna, ainda com Bearer).

## 7. Imagem (worker + api + site)

Construída na VPS a partir do commit (10-20 min: compila Tesseract 5.4.0 e o
React). A tag é o sha curto: é ela que permite o rollback do passo 16.

```bash
cd /srv/projeto-fopa
TAG=$(git rev-parse --short=12 HEAD)
git archive --format=tar HEAD | docker build -t fopa/worker:$TAG \
  --build-arg FOPA_GIT_SHA=$(git rev-parse HEAD) -f docker/worker.Dockerfile -
sed -i "s/^FOPA_IMAGEM_TAG=.*/FOPA_IMAGEM_TAG=$TAG/" docker/.env
grep -c "^FOPA_IMAGEM_TAG=$TAG$" docker/.env      # 1
```

(Alternativa: construir na máquina local e mandar com
`docker save fopa/worker:$TAG | gzip | ssh fopa@<vps> 'gunzip | docker load'`.
A medição de OCR de dentro dessa imagem é da CPU local: o passo 12 continua
obrigatório.)

## 8. Dados — caminho A ou B

**[REQUER APROVAÇÃO]** D6.

### 8A. Levar o estado local (dump + bucket)

Na **máquina local** (Git Bash; no PowerShell, sem o `MSYS_NO_PATHCONV=1`):

```bash
cd /c/Users/Nome/Projetos/projeto-fopa
# 1. backup COM o n8n de pé (o manifesto guarda a impressão da N8N_ENCRYPTION_KEY),
#    longe do horário dos schedules (W01 às 06:00), e logo depois congelar:
#    nada processa localmente daqui em diante.
python docker/backup.py                      # backups/<carimbo>/, "backup ok"
(cd docker && docker compose stop)
```

Credencial do rclone num arquivo gitignorado (`docker/.env.rclone` casa com
`.env.*`), para o segredo não ir parar em linha de comando nem no histórico:

```
RCLONE_CONFIG_R2_TYPE=s3
RCLONE_CONFIG_R2_PROVIDER=Cloudflare
RCLONE_CONFIG_R2_ACCESS_KEY_ID=<S3_KEY>
RCLONE_CONFIG_R2_SECRET_ACCESS_KEY=<S3_SECRET>
RCLONE_CONFIG_R2_ENDPOINT=https://<conta>.r2.cloudflarestorage.com
RCLONE_CONFIG_R2_REGION=auto
RCLONE_CONFIG_R2_NO_CHECK_BUCKET=true
```

```bash
# 2. o volume fopa_dados para o bucket: as chaves são as mesmas, o banco não muda
MSYS_NO_PATHCONV=1 docker run --rm --env-file docker/.env.rclone -v fopa_dados:/dados:ro \
  rclone/rclone:1.71 sync /dados r2:<bucket> --checksum --exclude ".put-*.tmp" --transfers 8 --progress
# 3. conferir: tudo que está no volume está no bucket, com o mesmo hash
MSYS_NO_PATHCONV=1 docker run --rm --env-file docker/.env.rclone -v fopa_dados:/dados:ro \
  rclone/rclone:1.71 check /dados r2:<bucket> --one-way --exclude ".put-*.tmp"
# 4. o backup e os segredos do n8n para a VPS (scp, nunca git)
scp -r backups/<carimbo> fopa@<vps>:/srv/projeto-fopa/backups/
scp -r n8n/.segredos fopa@<vps>:/srv/projeto-fopa/n8n/ && ssh fopa@<vps> chmod 700 /srv/projeto-fopa/n8n/.segredos
```

> **Depois do corte, nunca mais `rclone sync` da máquina local para o bucket.**
> `sync` apaga do destino o que não existe na origem, e o bucket passa a ter
> PDFs e RELATORIOs que só a VPS gravou. Se precisar mandar algo de novo, é
> `rclone copy`.
>
> **E a stack local não volta a processar.** Dois n8n com o W01/W10 ligados
> (local e VPS) processam as mesmas licitações duas vezes — com
> `provedor=claude`, é gasto dobrado.

Na **VPS** (restauração do `docker/backup.py`, com o override):

```bash
cd /srv/projeto-fopa/docker
B=../backups/<carimbo>
docker compose up -d fopa-postgres                  # o init cria o banco n8n e o papel n8n
docker exec -i fopa-postgres psql -U postgres < $B/globais.sql      # "already exists" p/ postgres e n8n: esperado
docker exec -i fopa-postgres pg_restore -U postgres -d fopa --exit-on-error < $B/fopa.dump
docker exec -i fopa-postgres pg_restore -U postgres -d n8n  --exit-on-error < $B/n8n.dump
docker compose --profile migrate run --rm fopa-migrate               # migrações novas + senhas do .env novo
```

### 8B. Do zero pelo acervo

Na VPS, com o snapshot congelado e o `amostras/` copiados por `rsync` para
`/srv/projeto-fopa/acervo/<snapshot>` e `/srv/projeto-fopa/amostras` (só
leitura para os containers):

```bash
cd /srv/projeto-fopa/docker
docker compose up -d fopa-postgres
docker compose --profile migrate run --rm fopa-migrate
FOPA_SNAPSHOT=<snapshot> docker compose --profile importar run --rm fopa-importar
docker compose --profile importar run --rm fopa-importar python -m migracao.publicar
```

O importador e o `publicar` gravam no volume `fopa_dados` da VPS (backend
`fs`). Levar ao bucket com o mesmo `rclone sync` do 8A, rodado na VPS, com um
`docker/.env.rclone` criado lá (`chmod 600`). Depois do passo 9, a regra de
escopo de hoje sobre o acervo (custo 0), como no `docker/README.md`:

```bash
docker compose exec fopa-worker python -c "import json,os,urllib.request as u; \
  r=u.Request('http://127.0.0.1:8000/escopo/reavaliar', data=b'{}', headers={'Authorization': \
  'Bearer '+os.environ['FOPA_WORKER_TOKEN'], 'Content-Type': 'application/json'}); \
  print(json.load(u.urlopen(r, timeout=300))['resultado'])"
```

## 9. Subir

```bash
cd /srv/projeto-fopa/docker
docker compose up -d fopa-postgres fopa-worker fopa-api fopa-n8n fopa-caddy
docker compose ps                                   # tudo running; worker e api healthy
docker compose logs fopa-caddy | grep -i "certificate obtained"      # um por domínio
curl -sS https://<site>/api/saude                   # {"ok":true,"caiu":[],"avisos":[]} (prod, sem sessão)
curl -sSI https://<n8n>/ | head -1                  # HTTP/2 401: basic auth
```

O `/health` do worker (sem porta: de dentro do container) tem de bater com o
local — git sha, Tesseract `5.4.0`, `tessdata_sha256` `c4932b93…` — e mostrar o
bucket:

```bash
docker compose exec fopa-worker python -c "import json,urllib.request as u; \
  h=json.load(u.urlopen('http://127.0.0.1:8000/health')); \
  print({k: h[k] for k in ('ok','git_sha','tesseract','tessdata_sha256','storage','anthropic_key_presente')})"
# storage: {'backend': 's3', 'raiz': 's3://<bucket>', ..., 'ok': True}; anthropic_key_presente: False
```

Invariante T24 no bucket (todo PDF/RELATORIO que o banco cita existe lá):

```bash
docker compose exec -T fopa-worker python - <<'EOF'
from api import banco, config, storage
cfg = config.carregar(); st = storage.abrir(cfg)
with banco.conectar(cfg) as c:
    chaves = [r[0] for r in c.execute("SELECT DISTINCT storage_key FROM arquivos WHERE status = 'ok' AND storage_key IS NOT NULL")]
    chaves += [r[0].split("://", 1)[-1].lstrip("/") for r in c.execute("SELECT DISTINCT html_uri FROM publicacoes WHERE html_uri IS NOT NULL")]
faltam = [k for k in chaves if not st.existe(k)]
print("objetos citados:", len(chaves), "| ausentes do bucket:", len(faltam), faltam[:5])
EOF
```

## 10. n8n: credenciais e fluxos

Os scripts rodam no host da VPS e falam com `127.0.0.1:5679` (loopback),
lendo o `docker/.env`:

```bash
cd /srv/projeto-fopa
python3 n8n/bootstrap.py      # A: entra com o owner.json copiado e regrava worker/site/postgres/smtp
                              # B: cria owner, chave da API e credenciais
python3 n8n/importar.py       # os fluxos DESTE commit, das folhas para a raiz, publicados
```

- **Editor**: `https://<n8n>/` (basic auth, depois o login do owner) ou por
  túnel, `ssh -L 5679:127.0.0.1:5679 fopa@<vps>` e `http://127.0.0.1:5679`.
- **`anthropicApi`**: criada à mão no editor (nunca em env de container;
  `ANTHROPIC_API_KEY` não existe em nenhum `.env`). No caminho A ela já veio no
  `n8n.dump`, cifrada com a mesma `N8N_ENCRYPTION_KEY`.
- **Gmail OAuth2 (opcional)**: nova URI no Google Cloud,
  `https://<n8n>/rest/oauth2-credential/callback`, e **reautorizar** a
  credencial (o token antigo foi emitido para o callback local).
- **n8n → worker por HTTPS + Bearer** (prova da F8), de dentro do container:

```bash
docker compose exec fopa-n8n node -e "require('https').get('https://fopa-worker-tls:8443/health', \
  r => { let b=''; r.on('data', d => b += d); r.on('end', () => console.log(r.statusCode, b.slice(0, 120))) }) \
  .on('error', e => console.log('ERRO', e.code))"      # 200 {"ok":true,...}
```

- Links de execução antigos (e-mails, site) continuam abrindo no caminho A:
  mesmo banco `n8n`, mesma chave, `EXECUTIONS_DATA_MAX_AGE=720` h.
- **W41 Histórico do PNCP** (27/09, ADR-023): roda
  sozinho todo dia às 04:30. Para a primeira rodada sem esperar,
  `nohup python3 n8n/executar.py W41 --timeout 3600 > /tmp/w41.log 2>&1 < /dev/null &` — fora da janela da
  esteira (passo 16): o job ocupa a única vaga do worker por ~20 min.

## 11. Login Google em produção

**[REQUER APROVAÇÃO]** D7. Google Cloud Console → APIs & Services →
Credentials → OAuth client ID (Web application):

- Authorized redirect URI: **`https://<site>/auth/google/callback`** — exatamente
  a que o `compose.prod.yml` deriva de `FOPA_DOMINIO_SITE` (o fluxo é todo no
  servidor; não precisa de "JavaScript origin").
- Consent screen com os escopos `openid email profile` (sem refresh token: a
  regra dos 7 dias do modo Testing não atinge o login do site, só a credencial
  Gmail do n8n).
- `GOOGLE_CLIENT_ID`/`GOOGLE_CLIENT_SECRET` no `docker/.env`, e
  `docker compose up -d fopa-api` para reler.

Quem entra é a allowlist da tabela `usuarios` (o administrador inicial vem da `012`; os
outros entram por `/admin`). Teste 11.6:

```bash
curl -s -o /dev/null -w "%{http_code}\n" https://<site>/api/licitacoes      # 401 sem cookie
curl -s -o /dev/null -w "%{http_code}\n" https://<site>/api/pdf/x/1         # 401 sem cookie, sempre
```

No navegador: o e-mail do administrador entra e `/api/me` diz `admin`; conta fora da
allowlist → 403 "peça acesso"; o `Set-Cookie` da sessão tem `Secure`
(DevTools → Application → Cookies); "p. N" num RELATORIO abre o PDF na página
(o `/api/pdf/...` responde 302 para o bucket com `X-Amz-Expires=600` e o
`#page=N` é reaplicado pelo navegador ao destino).

## 12. OCR baseline na VPS — ANTES de ligar o W22

Outra CPU, outro build: a equivalência com o host das medições é medida de
novo, nunca suposta (ADR-008; `tests/ocr_baseline/README.md`).

```bash
cd /srv/projeto-fopa/docker
docker compose exec fopa-worker python tests/ocr_baseline/medir.py --saida /tmp/ocr-vps.json
sha=$(docker inspect --format '{{.Id}}' fopa/worker:$(grep ^FOPA_IMAGEM_TAG= .env | cut -d= -f2) | cut -c8-19)
docker compose cp fopa-worker:/tmp/ocr-vps.json ../docs/ocr-equivalencia-$sha-vps.json
python3 -c "import json; a=json.load(open('../docs/ocr-equivalencia-d0db4059f800.json')); \
  b=json.load(open('../docs/ocr-equivalencia-$sha-vps.json')); \
  print('local', a['identicas'], a['similaridade_min'], '| vps', b['identicas'], b['similaridade_min'])"
```

**Medido na EC2 em 28/09/2026** (imagem `6ee29b4f0738`, id `fecdb629cdab`,
`docs/ocr-equivalencia-fecdb629cdab-vps.json`): 0/6 idênticas ao host antigo, mínima 0,9922 — página por
página a MESMA similaridade e a mesma contagem de caracteres da imagem medida no local (`d0db4059f800`), com o
mesmo binário do Tesseract (sha `ba3efa73…`) e o mesmo tessdata. A imagem é a referência, e a EC2 a reproduz.

Resultado diferente do local (d0db4059f800: 0/6 idênticas, mínima 0,9922) não
bloqueia, mas vira registro: o JSON vai para o repositório (com commit) e,
se mudar, a decisão "a imagem é a referência" passa a citar a medição da VPS.

## 13. Provas da F8 e virar a chave

| Prova | Comando / onde |
|---|---|
| `/health` igual ao local | passo 9 |
| a chave da Anthropic não está em container | `docker inspect fopa-worker fopa-api --format '{{range .Config.Env}}{{println .}}{{end}}' \| grep -c ANTHROPIC` → `0` |
| `/` do n8n pede autenticação; webhook público | `curl -sI https://<n8n>/` → 401; `curl -s -X POST https://<n8n>/webhook/fopa/verificar -H "X-FOPA-Token: $(grep ^FOPA_SITE_TOKEN= docker/.env \| cut -d= -f2)" -H "Content-Type: application/json" -d '{}'` → 202 em < 1 s (busca no PNCP, custo R$ 0) |
| 11.3 PNCP vivo da VPS | `buscas` com `cobertura_pct` depois do verificar; `/execucoes` no site |
| 11.9 e-mail sai da VPS | `/emails` no site: `canal` e `status='enviado'` |
| PDF por URL assinada | passo 11 |

Só então **[REQUER APROVAÇÃO]** D12, ligar a esteira: nos JSON versionados, tirar
`"disabled": true` de dois nós — o gatilho "A cada 10 min" do `n8n/workflows/W10.json`
e o "W10 Fila (sem esperar)" do `n8n/workflows/W01.json` —, commitar e rodar
`python3 n8n/importar.py` (o `test_w01` e o `test_w10_w11` conferem os dois nós
desligados: ajuste os dois testes no mesmo commit). Conferir `orcamento.auto_processar`: `true`, a agenda do W10
reivindica; `false`, só o site e o Manual processam. Sem este passo a próxima
licitação nova é descoberta e fica parada em `nova`.

E **[REQUER APROVAÇÃO]** D10: `/admin` → provedor `claude` (o site pede
confirmação). A próxima licitação nova é processada na nuvem; conferir
`execucoes_modelo.origem='api'` com `brl` conhecido e os e-mails "carregada" e
"processada".

## 14. Backup no cron

```bash
crontab -e
# banco fopa + banco n8n + export cifrado do n8n, retenção 7 (docker/backup.py)
15 3 * * *  cd /srv/projeto-fopa && python3 docker/backup.py >> backups/backup.log 2>&1
# domingo: restaura o mais recente num Postgres efêmero e compara as contagens
45 3 * * 0  cd /srv/projeto-fopa && python3 docker/backup.py --verificar >> backups/backup.log 2>&1
```

O `backup.py` usa `docker exec` (não precisa de porta de Postgres) e mexe só
nos containers do projeto `fopa`. Ele **não** copia o bucket nem sai da VPS:

- **[REQUER APROVAÇÃO]** D9 — cópia fora da VPS, depois do backup
  (`30 3 * * *`): `rclone copy /srv/projeto-fopa/backups <remoto-de-backup>:fopa-backups`
  com uma credencial que não apaga nada no destino.
- Bucket: os objetos são content-addressed e o site nunca apaga; uma cópia
  periódica com `rclone copy r2:<bucket> <remoto-de-backup>:<bucket>-copia` basta.
  PDFs perdidos também voltam do PNCP (o W21 confere o sha256), RELATORIOs pelo
  `/render`.
- A `N8N_ENCRYPTION_KEY` fica no cofre, nunca no backup: o manifesto guarda só
  os 12 primeiros hex do sha256 dela, para conferir a chave na restauração.

> [!success] Estado na EC2 em 28/09/2026
> **Feito.** `crontab` do usuário `fopa` (fuso America/Sao_Paulo): 03:15 `backup.py` (retenção 7, conta os
> manuais), 03:35 `backup_fora.py` (D9: cada backup `ok` sobe para `s3://fopa-editais-1/backups/<carimbo>/`,
> classe STANDARD_IA, com a credencial `fopa-app`, que não apaga; o S3 confere o sha256 de cada arquivo contra
> o manifesto) e domingo 03:45 `backup.py --verificar`. Primeira carga: os 7 backups locais, ~4,6 GB em 98 s.
> Restauração de prova em 28/09: 147 s, contagens iguais ao manifesto, memória disponível mínima ~800 MB.
> Regra de ciclo de vida `backups-expiram-30-dias` (28/09, console): só o prefixo `backups/`, expira em 30 dias;
> o bucket não tem versionamento, então expirar apaga de fato. No bucket ficam ~30 cópias (~20 GB).

## 15. Restauração

Banco (VPS existente ou nova, depois dos passos 2-7):

```bash
cd /srv/projeto-fopa/docker
docker compose stop fopa-n8n fopa-worker fopa-api
# volume novo: docker compose down; docker volume rm fopa_postgres_data  (SÓ se é para trocar tudo)
docker compose up -d fopa-postgres
# ...os mesmos 4 comandos de restauração do 8A (globais, fopa.dump, n8n.dump, fopa-migrate)
docker compose up -d
python3 docker/backup.py --verificar ../backups/<carimbo>     # opcional: prova do backup em efêmero
```

- A `N8N_ENCRYPTION_KEY` do `.env` tem de ser a do backup (confira com o
  `n8n_chave_sha256_12` do `manifesto.json`).
- Bucket: `rclone copy <remoto-de-backup>:<bucket>-copia r2:<bucket>` e a
  checagem T24 do passo 9.
- VPS perdida inteira: VPS nova (passos 2-7), backup trazido do destino fora
  da VPS, restauração acima, passo 10 (`bootstrap.py` + `importar.py`) e DNS
  apontando para o IP novo.

## 16. Atualizar e voltar (rollback de imagem)

Atualizar:

```bash
cd /srv/projeto-fopa && git pull
python3 docker/backup.py                                   # ANTES de migrar: é o ponto de volta
TAG=$(git rev-parse --short=12 HEAD)
git archive --format=tar HEAD | docker build -t fopa/worker:$TAG \
  --build-arg FOPA_GIT_SHA=$(git rev-parse HEAD) -f docker/worker.Dockerfile -
grep ^FOPA_IMAGEM_TAG= docker/.env                         # anote a tag ANTERIOR
sed -i "s/^FOPA_IMAGEM_TAG=.*/FOPA_IMAGEM_TAG=$TAG/" docker/.env
cd docker && docker compose --profile migrate run --rm fopa-migrate
docker compose up -d fopa-worker fopa-api
cd .. && python3 n8n/importar.py                            # fluxos deste commit
```

Voltar para a versão anterior:

```bash
cd /srv/projeto-fopa && git checkout <sha-anterior>
sed -i "s/^FOPA_IMAGEM_TAG=.*/FOPA_IMAGEM_TAG=<tag-anterior>/" docker/.env
cd docker && docker compose up -d fopa-worker fopa-api
cd .. && python3 n8n/importar.py                            # fluxos da versão anterior
```

- As migrações só avançam. Se a versão nova aplicou uma migração que o código
  anterior não entende (o `/api/saude` e as rotas dizem 503 com o nome do
  objeto), a volta inclui o banco: restaurar o backup tirado antes de migrar
  (passo 15). Tudo que entrou depois dele se perde — por isso o backup é o
  primeiro comando da atualização.
- Manter as 3 últimas imagens (`docker image ls fopa/worker`); apagar as
  mais velhas com `docker image rm fopa/worker:<tag>`, nunca `prune -a` às cegas.
- **Imagem feita na máquina local** (é como a EC2 recebe desde 26/09, ADR-022 — a t3.small não compila bem):
  `git push vps v3`, e na máquina local
  `git archive --format=tar HEAD | docker build -t fopa/worker:$TAG --build-arg FOPA_GIT_SHA=$(git rev-parse HEAD) -f docker/worker.Dockerfile -`
  e `docker save fopa/worker:$TAG | gzip -1 | ssh fopa 'gunzip | docker load'`; o resto (tag, migrar, subir,
  importar) segue igual, na VPS. **Não** pôr `< /dev/null` nesse `ssh`: ele troca a entrada e o `docker load`
  recebe nada ("unrecognized image format").

> [!risco] A janela da esteira — não reiniciar o worker nela
> Com `FOPA_JOBS_CONCORRENCIA=1` (produção, ADR-022), o worker tem **uma** vaga de job. Recriar o `fopa-worker`
> **das 06:00 às 07:50** (o W10 dispara a cada 10 min) perde o job em andamento, e os que estavam na fila ficam
> `queued` para sempre na tabela `jobs` — o laço do W21/W22 esgota e a licitação vai para `erro_leitura` (volta
> sozinha pela fila, mas volta tarde). Longe também das **04:30** (o W41 ocupa a vaga ~20 min). Olhar "não há job
> rodando" não basta: o W10 abre job novo a cada 10 min. Aconteceu em 27/09 às 06:13 — 9 erros no W20.
> Mudança só da API ou do site: `docker compose up -d --no-deps fopa-api`, e o worker fica para depois da janela.

## 17. Limitações e armadilhas (plano, seção 12)

- **URL assinada vale 10 min.** O navegador baixa o PDF inteiro logo depois de
  abrir; um PDF enorme lido por mais de 10 min antes de terminar de baixar
  falha nas páginas que faltam — basta clicar de novo no link do site (outra
  URL). Recarregar a aba do PDF não serve: a URL velha expirou.
- **Cloudflare laranja corta em 100 s.** Só vale para requisições que entram
  por ele; o W11 responde 202 na hora e o n8n chama a Anthropic direto (até
  600 s), sem proxy no meio.
- **OCR em outra CPU**: passo 12 antes do W22, sempre que a imagem ou a VPS mudar.
- **Segredos**: `docker compose config` sem `--quiet` imprime todos; o `.env`
  local nunca vai para a VPS; `ANTHROPIC_API_KEY` só na Credential do n8n.
- **Docker ignora o ufw** (passo 2): nenhuma porta nova no compose sem `127.0.0.1:`.
- **Dois n8n processando** (local e VPS) = gasto dobrado (8A).
- **`rclone sync` depois do corte** apaga o que só a VPS gravou (8A).
- **Certificados do Caddy** ficam no volume `fopa_caddy_data`: apagá-lo força
  reemissão, e o Let's Encrypt limita emissões por semana.

## 18. Stack local para desenvolver (sem agenda)

A produção é a EC2; a stack local só sobe para desenvolver e ensaiar fluxos (v3.1, 28/09/2026). O perigo é o n8n
local com os fluxos **agendados** publicados: W01/W41 batendo no PNCP e o W50 mandando e-mail da fila local pelo
Resend — em dobro com a produção. Por isso, **antes** de o n8n subir, tudo é despublicado no banco local:

```bash
cd docker && docker compose up -d fopa-postgres          # só o banco
docker exec -i fopa-postgres psql -U postgres -d n8n -c \
  "UPDATE workflow_entity SET active = false, \"activeVersionId\" = NULL"
docker compose up -d fopa-worker fopa-api fopa-n8n       # o log do n8n diz "0 published workflows"
cd .. && python n8n/importar.py --publicar W20,W21,W22,W23,W24,W90   # só os subfluxos (sem agenda)
python n8n/executar.py W20 --itens '{"controle": "...", "forcar": true}'   # roda à mão
```

- Os testes de `n8n/tests` que dependem da stack **publicam** fluxos com agenda (W00, W50, W90): não rodar na
  stack religada sem antes esvaziar a fila `emails` local.
- Parar: `docker compose stop` (a stack volta a ficar congelada).
