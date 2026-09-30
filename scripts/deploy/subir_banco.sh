#!/usr/bin/env bash
# Leva o banco local (fopa + n8n) para o servidor de produção e congela a stack
# local — docs/DEPLOY.md, passo 8A (backup, congelar, scp, restauração na VPS).
#
# Uso (Git Bash, com o Docker Desktop e a stack local de pé):
#   scripts/deploy/subir_banco.sh                 # backup novo, congela, envia, restaura
#   scripts/deploy/subir_banco.sh --backup backups/2026-09-26_170000   # reaproveita um backup
#   scripts/deploy/subir_banco.sh --forcar        # restaura por cima de um banco que já tem dados
#   scripts/deploy/subir_banco.sh --sim           # não pergunta antes de congelar
#
# Ordem das travas, antes de mexer em qualquer coisa:
#   1. a N8N_ENCRYPTION_KEY do servidor é a mesma do local (sem ela as
#      credenciais do n8n restauradas não abrem);
#   2. o banco `fopa` do servidor está vazio (ou --forcar): um segundo uso não
#      sobrescreve o que a produção já gravou.
# Depois do congelamento a stack local NÃO volta a processar: dois n8n com o
# W01/W10 ligados processam as mesmas licitações duas vezes (gasto dobrado).
set -euo pipefail

RAIZ=$(cd "$(dirname "$0")/../.." && pwd)
VPS=${FOPA_VPS:-fopa}
DESTINO=/srv/projeto-fopa

falha() { echo "ERRO: $*" >&2; exit 1; }
uso() { sed -n '2,19p' "$0" | sed 's/^# \{0,1\}//'; exit 0; }

backup=""
forcar=0
sim=0
while [ $# -gt 0 ]; do
  case "$1" in
    --backup) [ $# -ge 2 ] || falha "--backup pede a pasta"; backup=$2; shift ;;
    --forcar) forcar=1 ;;
    --sim) sim=1 ;;
    -h|--help) uso ;;
    *) falha "opção desconhecida: $1 (veja --help)" ;;
  esac
  shift
done

cd "$RAIZ"
ssh_vps() { ssh -o BatchMode=yes -o ConnectTimeout=15 "$VPS" "$@"; }

# ---------------------------------------------------------------- 0. pré-condições
docker info >/dev/null 2>&1 || falha "o Docker não está rodando (abra o Docker Desktop)"
ssh_vps true || falha "não consegui entrar em $VPS por SSH (~/.ssh/config, Host $VPS)"

# impressão (12 hex do sha256) da N8N_ENCRYPTION_KEY, sem revelar a chave
impressao_local=$(grep -m1 '^N8N_ENCRYPTION_KEY=' docker/.env | cut -d= -f2- | tr -d '\r\n' | sha256sum | cut -c1-12)
impressao_vps=$(ssh_vps "grep -m1 '^N8N_ENCRYPTION_KEY=' $DESTINO/docker/.env | cut -d= -f2- | tr -d '\r\n' | sha256sum | cut -c1-12")
[ "$impressao_local" != "$(printf '' | sha256sum | cut -c1-12)" ] || falha "N8N_ENCRYPTION_KEY vazia no docker/.env local"
[ "$impressao_local" = "$impressao_vps" ] || falha "a N8N_ENCRYPTION_KEY do servidor ($impressao_vps) é diferente da local ($impressao_local): as credenciais do n8n não abririam"
echo "== N8N_ENCRYPTION_KEY igual nos dois lados ($impressao_local)"

echo "== subindo só o Postgres do servidor e conferindo se o banco fopa está vazio"
linhas=$(ssh_vps "bash -s" <<'REMOTO'
set -euo pipefail
cd /srv/projeto-fopa/docker
docker compose up -d fopa-postgres >/dev/null 2>&1
for _ in $(seq 1 60); do
  [ "$(docker inspect -f '{{.State.Health.Status}}' fopa-postgres 2>/dev/null)" = healthy ] && break
  sleep 2
done
docker exec fopa-postgres psql -U postgres -d postgres -tAc \
  "select coalesce((select 1 from pg_database where datname='fopa'),0)" | grep -q 1 || { echo 0; exit 0; }
# Duas consultas: o Postgres valida a query inteira antes de rodar, e um CASE
# que cita `licitacoes` falha quando a tabela ainda não existe.
[ "$(docker exec fopa-postgres psql -U postgres -d fopa -tAc "select to_regclass('public.licitacoes') is not null")" = t ] || { echo 0; exit 0; }
docker exec fopa-postgres psql -U postgres -d fopa -tAc "select count(*) from licitacoes"
REMOTO
)
linhas=$(echo "$linhas" | tr -d '[:space:]')
if [ "${linhas:-0}" != 0 ] && [ "$forcar" = 0 ]; then
  falha "o banco fopa do servidor já tem $linhas licitação(ões). Para restaurar por cima, rode com --forcar"
fi
echo "   licitações no servidor hoje: ${linhas:-0}"

# ---------------------------------------------------------------- 1. backup local
if [ -z "$backup" ]; then
  docker ps -q --filter name=^fopa-n8n$ | grep -q . || falha "o fopa-n8n local está parado: o backup precisa dele de pé para exportar fluxos e credenciais"
  echo "== backup local (docker/backup.py)"
  python docker/backup.py || falha "o backup falhou (saída 2 = parcial; não siga com backup parcial)"
  backup=$(ls -dt backups/20*/ 2>/dev/null | head -1)
  backup=${backup%/}
fi
[ -d "$backup" ] || falha "pasta de backup não encontrada: $backup"
for f in fopa.dump n8n.dump globais.sql manifesto.json; do
  [ -s "$backup/$f" ] || falha "$backup/$f ausente ou vazio"
done
carimbo=$(basename "$backup")
echo "== backup: $backup"

# ---------------------------------------------------------------- 2. congelar o local
if [ "$sim" = 0 ]; then
  printf 'Congelar a stack local agora? Ela não deve voltar a processar depois disso. [s/N] '
  read -r resp
  case "$resp" in s|S|sim|SIM) ;; *) falha "cancelado antes de congelar; nada foi enviado" ;; esac
fi
echo "== congelando a stack local (docker compose stop)"
(cd docker && docker compose stop)

# ---------------------------------------------------------------- 3. enviar
echo "== enviando o backup e os segredos do n8n para $VPS (scp)"
ssh_vps "mkdir -p $DESTINO/backups $DESTINO/n8n"
scp -q -r -o BatchMode=yes "$backup" "$VPS:$DESTINO/backups/"
scp -q -r -o BatchMode=yes n8n/.segredos "$VPS:$DESTINO/n8n/"
ssh_vps "chmod 700 $DESTINO/n8n/.segredos && chmod 600 $DESTINO/n8n/.segredos/*"

# ---------------------------------------------------------------- 4. restaurar no servidor
echo "== restaurando no servidor"
ssh_vps "bash -s -- '$carimbo' '$forcar'" <<'REMOTO'
set -euo pipefail
carimbo=$1
forcar=$2
cd /srv/projeto-fopa/docker
B=../backups/$carimbo
limpar=()
[ "$forcar" = 1 ] && limpar=(--clean --if-exists)
# "role ... already exists" para postgres e n8n é esperado: sem ON_ERROR_STOP.
docker exec -i fopa-postgres psql -U postgres -q < "$B/globais.sql" 2>&1 | grep -v 'already exists' || true
docker exec -i fopa-postgres pg_restore -U postgres -d fopa --exit-on-error "${limpar[@]}" < "$B/fopa.dump"
docker exec -i fopa-postgres pg_restore -U postgres -d n8n --exit-on-error "${limpar[@]}" < "$B/n8n.dump"
docker compose --profile migrate run --rm fopa-migrate
echo "licitações restauradas: $(docker exec fopa-postgres psql -U postgres -d fopa -tAc 'select count(*) from licitacoes')"
REMOTO

echo "banco ok: $carimbo restaurado em $VPS. A stack local está congelada."
echo "Próximo: scripts/deploy/subir_bucket.sh --executar (sync final do volume, antes de subir o servidor)"
