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
VITE_MCHAT_EDITION=core npm run build:core

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
  ENV_FILE="$PROJECT_DIR/ops/deploy/.env.production.generated"
  cat > "$ENV_FILE" <<'EOF'
DATABASE_URL=mysql+aiomysql://mchat:CHANGE_ME@127.0.0.1:3306/mchat

JWT_SECRET=__JWT_SECRET__
JWT_ALGORITHM=HS256
JWT_EXPIRE_MINUTES=10080

ADMIN_USERNAME=admin
ADMIN_PASSWORD=admin123

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
  sed -i '' "s/__JWT_SECRET__/${JWT_SECRET}/g" "$ENV_FILE"
  rsync -avz "$ENV_FILE" "${REMOTE}:${REMOTE_DIR}/.env"
fi

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
for patent_skill in patent-search patent-transaction patent-disclosure patent-report; do
  sync_skill_dir "$patent_skill"
done

echo "==> Remote setup (Core backend: app.main:app)"
ssh "$REMOTE" "chmod +x ${REMOTE_DIR}/ops/deploy/remote-setup.sh && bash ${REMOTE_DIR}/ops/deploy/remote-setup.sh"

echo ""
echo "Core deployed to http://mchat.chat"
echo "  Admin:  http://mchat.chat/admin"
echo "  API:    http://mchat.chat/docs"
