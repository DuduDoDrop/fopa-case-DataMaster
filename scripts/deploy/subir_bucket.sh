#!/usr/bin/env bash
# Leva o volume local `fopa_dados` (PDFs e RELATORIOs) para o bucket S3 de
# produção — docs/DEPLOY.md, passo 8A, itens 2 e 3.
#
# Uso (Git Bash, na raiz do repo ou de qualquer lugar):
#   scripts/deploy/subir_bucket.sh              # ENSAIO: mostra o que enviaria, não envia nada
#   scripts/deploy/subir_bucket.sh --executar   # sync de verdade + rclone check (mesmo hash)
#   scripts/deploy/subir_bucket.sh --executar --copy   # depois do corte: só acrescenta, nunca apaga
#
# Credencial: n8n/.segredos/s3-prod.env (gitignorado), com
#   S3_BUCKET=fopa-editais-1  S3_REGION=sa-east-1  S3_KEY=AKIA...  S3_SECRET=...
# Ela vira um arquivo temporário do rclone (chmod 600, apagado na saída): o
# segredo não passa por linha de comando nem pelo histórico.
#
# Trava do corte: `sync` apaga do bucket o que não existe no volume local. Depois
# que a stack do servidor sobe, o worker de lá grava PDFs no bucket que o local
# não tem — um `sync` apagaria esses arquivos. Por isso, se o fopa-worker do
# servidor estiver rodando, o script recusa `sync` e só aceita `--copy`.
set -euo pipefail

RAIZ=$(cd "$(dirname "$0")/../.." && pwd)
CRED="$RAIZ/n8n/.segredos/s3-prod.env"
VOLUME=fopa_dados
IMAGEM=rclone/rclone:1.71
VPS=${FOPA_VPS:-fopa}
EXCLUIR='.put-*.tmp'

falha() { echo "ERRO: $*" >&2; exit 1; }
uso() { sed -n '2,20p' "$0" | sed 's/^# \{0,1\}//'; exit 0; }

modo=ensaio
op=sync
checar_vps=1
for a in "$@"; do
  case "$a" in
    --executar) modo=executar ;;
    --copy) op=copy ;;
    --sem-checar-vps) checar_vps=0 ;;
    -h|--help) uso ;;
    *) falha "opção desconhecida: $a (veja --help)" ;;
  esac
done

# ---------------------------------------------------------------- credencial
[ -f "$CRED" ] || falha "falta $CRED (crie as chaves do usuário IAM fopa-app; formato no --help)"
S3_BUCKET="" S3_REGION="" S3_KEY="" S3_SECRET=""
while IFS='=' read -r k v || [ -n "$k" ]; do   # `|| -n` lê a última linha sem \n
  v=${v%$'\r'}
  case "$k" in
    S3_BUCKET) S3_BUCKET=$v ;;
    S3_REGION) S3_REGION=$v ;;
    S3_KEY) S3_KEY=$v ;;
    S3_SECRET) S3_SECRET=$v ;;
  esac
done < "$CRED"
for var in S3_BUCKET S3_REGION S3_KEY S3_SECRET; do
  [ -n "${!var}" ] || falha "$var vazio em $CRED"
done

# ---------------------------------------------------------------- pré-condições
docker info >/dev/null 2>&1 || falha "o Docker não está rodando (abra o Docker Desktop)"
docker volume inspect "$VOLUME" >/dev/null 2>&1 || falha "volume $VOLUME não existe nesta máquina"

if [ "$op" = sync ] && [ "$checar_vps" = 1 ]; then
  echo "== conferindo se o worker do servidor ($VPS) já está de pé"
  if ! rodando=$(ssh -o BatchMode=yes -o ConnectTimeout=10 "$VPS" "docker ps -q --filter name=^fopa-worker$" 2>/dev/null); then
    falha "não consegui falar com $VPS por SSH para conferir o corte; use --copy, ou --sem-checar-vps se tem certeza de que o servidor ainda não subiu"
  fi
  if [ -n "$rodando" ]; then
    falha "o fopa-worker do servidor está rodando: o bucket já pode ter arquivos que só a produção gravou. sync apagaria esses arquivos — use --copy"
  fi
  echo "   servidor ainda sem worker: sync liberado"
fi

# ---------------------------------------------------------------- config do rclone
mkdir -p "$RAIZ/backups"
envfile=$(mktemp "$RAIZ/backups/.rclone-env.XXXXXX")
trap 'rm -f "$envfile"' EXIT
chmod 600 "$envfile"
cat > "$envfile" <<EOF
RCLONE_CONFIG_S3_TYPE=s3
RCLONE_CONFIG_S3_PROVIDER=AWS
RCLONE_CONFIG_S3_ACCESS_KEY_ID=$S3_KEY
RCLONE_CONFIG_S3_SECRET_ACCESS_KEY=$S3_SECRET
RCLONE_CONFIG_S3_REGION=$S3_REGION
RCLONE_CONFIG_S3_LOCATION_CONSTRAINT=$S3_REGION
RCLONE_CONFIG_S3_NO_CHECK_BUCKET=true
EOF
# O docker.exe do Windows precisa do caminho no formato C:\...; no Linux fica igual.
envfile_docker=$(cygpath -w "$envfile" 2>/dev/null || echo "$envfile")

rclone() {
  MSYS_NO_PATHCONV=1 docker run --rm --env-file "$envfile_docker" \
    -v "$VOLUME:/dados:ro" "$IMAGEM" "$@"
}

echo "== origem: volume $VOLUME"
rclone size /dados --exclude "$EXCLUIR"
echo "== destino: s3:$S3_BUCKET ($S3_REGION)"
rclone size "s3:$S3_BUCKET" || falha "não consegui ler o bucket (chave, região ou política do fopa-app?)"

if [ "$modo" = ensaio ]; then
  log="$RAIZ/backups/rclone-ensaio-$(date +%Y%m%d-%H%M%S).log"
  echo "== ENSAIO ($op --dry-run): nada é enviado nem apagado"
  rclone "$op" /dados "s3:$S3_BUCKET" --checksum --exclude "$EXCLUIR" --dry-run > "$log" 2>&1 || falha "o ensaio falhou; veja $log"
  echo "   enviaria:  $(grep -c 'Skipped copy' "$log" || true) arquivo(s)"
  echo "   apagaria:  $(grep -c 'Skipped delete' "$log" || true) arquivo(s) do bucket"
  echo "   detalhe em $log"
  sufixo=""; [ "$op" = copy ] && sufixo=" --copy"
  echo "Para enviar de verdade: $0 --executar$sufixo"
  exit 0
fi

echo "== $op de verdade"
rclone "$op" /dados "s3:$S3_BUCKET" --checksum --exclude "$EXCLUIR" --transfers 8 --stats 30s --stats-one-line -v
echo "== conferindo: tudo que está no volume está no bucket, com o mesmo hash"
rclone check /dados "s3:$S3_BUCKET" --one-way --exclude "$EXCLUIR"
echo "bucket ok"
