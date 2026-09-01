#!/bin/bash
# Deploy mchat Core (standalone vertical RAG, no Cloud features) to remote server.
# Usage: bash ops/scripts/deploy-remote-core.sh
set -euo pipefail

REMOTE="${1:-${MCHAT_DEPLOY_REMOTE:-}}"
REMOTE="${REMOTE:?Set MCHAT_DEPLOY_REMOTE or pass user@host as first argument}"
REMOTE_DIR="${MCHAT_DEPLOY_DIR:-/opt/xiaoxiao/mchat}"
PROJECT_DIR="$(cd "$(dirname "$0")/../.." && pwd)"

echo "==> Build frontend (Core edition)"
cd "$PROJECT_DIR/src/frontend"
VITE_MCHAT_SIGNUP_ENABLED=true npm run build:core

echo "==> Rsync to ${REMOTE}:${REMOTE_DIR}"
rsync -avz --delete \
  --exclude '.git' \
  --exclude 'node_modules' \
  --exclude 'src/frontend/node_modules' \
  --exclude 'src/backend/venv' \
  --exclude '__pycache__' \
  --exclude '*.pyc' \
  --exclude '.env' \
  --exclude 'ops/deploy/.env.production.generated' \
  --exclude 'src/backend/logs' \
  --exclude 'logs' \
  --exclude 'skills' \
  --exclude '/data/' \
  --exclude 'uploads' \
  --exclude 'test.db' \
  --exclude '.pytest_cache' \
  --exclude 'src/frontend/.vite' \
  "$PROJECT_DIR/" "${REMOTE}:${REMOTE_DIR}/"

# Preserve existing server .env; only bootstrap if missing
if ssh "$REMOTE" "test -f ${REMOTE_DIR}/.env"; then
  echo "==> Keep existing ${REMOTE_DIR}/.env on server"
else
  echo "==> Create initial .env on server"
  JWT_SECRET=$(openssl rand -hex 32)
  ADMIN_PASSWORD=$(openssl rand -hex 18)
  ENV_FILE="$PROJECT_DIR/ops/deploy/.env.production.generated"
  umask 077
  cat > "$ENV_FILE" <<'EOF'
DATABASE_URL=mysql+aiomysql://mchat:CHANGE_ME@127.0.0.1:3306/mchat

JWT_SECRET=__JWT_SECRET__
JWT_ALGORITHM=HS256
JWT_EXPIRE_MINUTES=10080

ADMIN_USERNAME=admin
ADMIN_PASSWORD=__ADMIN_PASSWORD__
ENVIRONMENT=production
SHOW_BOOTSTRAP_CREDENTIALS=false
MCHAT_SIGNUP_ENABLED=true

SERVER_HOST=0.0.0.0
SERVER_PORT=3001

MILVUS_ENABLED=false
MILVUS_HOST=localhost
MILVUS_PORT=19530

SKILLS_DIR=/opt/xiaoxiao/mchat/skills
UPLOAD_DIR=/opt/xiaoxiao/mchat/data/uploads
MAX_UPLOAD_SIZE_MB=50

EMBEDDING_PROVIDER=openai
EMBEDDING_MODEL=text-embedding-3-small
EOF
  sed -i.bak \
    -e "s/__JWT_SECRET__/${JWT_SECRET}/g" \
    -e "s/__ADMIN_PASSWORD__/${ADMIN_PASSWORD}/g" \
    "$ENV_FILE"
  rm -f "$ENV_FILE.bak"
  rsync -avz "$ENV_FILE" "${REMOTE}:${REMOTE_DIR}/.env"
fi

echo "==> Enforce production security mode in server .env"
ssh "$REMOTE" "MCHAT_ENV_FILE='${REMOTE_DIR}/.env' bash -s" <<'REMOTE_ENV'
set -euo pipefail

upsert_env() {
  local key="$1"
  local value="$2"
  if grep -q "^${key}=" "$MCHAT_ENV_FILE"; then
    sed -i "s#^${key}=.*#${key}=${value}#" "$MCHAT_ENV_FILE"
  else
    printf '\n%s=%s\n' "$key" "$value" >> "$MCHAT_ENV_FILE"
  fi
}

upsert_env ENVIRONMENT production
upsert_env SHOW_BOOTSTRAP_CREDENTIALS false
upsert_env MCHAT_SIGNUP_ENABLED true
chmod 600 "$MCHAT_ENV_FILE"
REMOTE_ENV

echo "==> Ensure GameCenter devbridge env hints on server .env"
ssh "$REMOTE" "ENV_FILE='${REMOTE_DIR}/.env'; if [ -f \"\$ENV_FILE\" ] && ! grep -q 'GAMECENTER_BRIDGE_ENABLED' \"\$ENV_FILE\"; then cat >> \"\$ENV_FILE\" <<GCENV

# GameCenter devbridge (enable after verifying source_root on this host)
# GameCenter admin UI often runs at http://10.98.8.15:5099
# GAMECENTER_BRIDGE_ENABLED=true
# GAMECENTER_SOURCE_ROOT=/opt/xiaoxiao/gamecenter/src
# GAMECENTER_BRIDGE_WRITE_ENABLED=false
# GAMECENTER_BRIDGE_DATA_ROOT=${REMOTE_DIR}/data/devbridge/gamecenter
# GAMECENTER_BUILD_COMMAND=bash /opt/xiaoxiao/mchat/ops/scripts/gamecenter-remote-pipeline-build.sh {slug}
# GAMECENTER_AUTO_BUILD_AFTER_PATCH=true
# GAMECENTER_BUILD_SSH_HOST=192.168.x.x
# GAMECENTER_BUILD_SSH_USER=build
# GAMECENTER_BUILD_PIPELINE_SCRIPT=/opt/mchat/ops/scripts/gamecenter-local-pipeline.sh
# GAMECENTER_DEPLOY_HOST=10.98.8.15
# MCHAT_SIGNUP_ENABLED=true
# GAMECENTER_BUILD_SSH_HOST=10.98.8.186
# GAMECENTER_BUILD_SSH_USER=你的Windows用户名
# GAMECENTER_PUBLISH_ENABLED=true
# GAMECENTER_PLAYABLES_ROOT=/opt/xiaoxiao/gamecenter/playables
# GAMECENTER_SYNC_EXTRACTED_ROOT=/opt/xiaoxiao/gamecenter/_extracted
# GAMECENTER_PLAYABLE_BASE_URL=http://10.98.8.15:5099
GCENV
fi"

echo "==> Fix frontend dist permissions on server (nginx in Docker must read static files)"
ssh "$REMOTE" "chmod -R a+rX ${REMOTE_DIR}/src/frontend/dist ${REMOTE_DIR}/src/frontend/public 2>/dev/null || true"

sync_skill_dir() {
  local name="$1"
  local src="$PROJECT_DIR/skills/$name"
  [ -d "$src" ] || return 0
  echo "==> Sync skills/$name (overwrite)"
  ssh "$REMOTE" "mkdir -p ${REMOTE_DIR}/skills/$name"
  rsync -avz --delete \
    --exclude '__pycache__/' \
    --exclude '.DS_Store' \
    --exclude 'config.json' \
    --exclude 'dist/' \
    "$src/" "${REMOTE}:${REMOTE_DIR}/skills/$name/"
}

sync_skill_dir mchat-help
sync_skill_dir mchat-ops
sync_skill_dir dev-assistant
sync_skill_dir gamecenter-dev-agent
sync_skill_dir git-commit-writer
sync_skill_dir code-reviewer
sync_skill_dir wheelchair-advisor
for patent_skill in patent-search patent-transaction patent-disclosure patent-report; do
  sync_skill_dir "$patent_skill"
done

# StockIntelligence skills（每个内嵌 si_common，独立可加载）
for stock_skill in stock-quote stock-capital stock-fundamentals stock-research stock-news stock-announcement stock-sentiment stock-analysis; do
  sync_skill_dir "$stock_skill"
done

echo "==> Refresh tenant patent-search copies (Widget uses tenant workspace skills)"
ssh "$REMOTE" "set -euo pipefail
REMOTE_DIR='${REMOTE_DIR}'
for d in \"\${REMOTE_DIR}\"/data/tenants/*/skills/patent-search; do
  [ -d \"\$d\" ] || continue
  echo \"  -> \$d\"
  rsync -a --delete \
    --exclude '__pycache__/' \
    --exclude '.DS_Store' \
    --exclude 'config.json' \
    \"\${REMOTE_DIR}/skills/patent-search/\" \"\$d/\"
done"

echo "==> Remote setup (Core backend: app.main:app)"
ssh "$REMOTE" "chmod +x ${REMOTE_DIR}/ops/scripts/gamecenter-*.sh ${REMOTE_DIR}/ops/scripts/resolve-gamecenter-project.py ${REMOTE_DIR}/ops/deploy/remote-setup.sh && bash ${REMOTE_DIR}/ops/deploy/remote-setup.sh"

echo ""
echo "Core deployed to ${REMOTE} (${REMOTE_DIR})"
echo "  生产域名: http://mchat.9235.net (Admin: /admin, API: /docs)"
echo "  Admin:  http://${REMOTE}/admin"
echo "  API:    http://${REMOTE}/docs"
