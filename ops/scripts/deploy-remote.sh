#!/bin/bash
# Deploy mchat to remote server (incremental update; preserves DB, .env, skills, uploads)
# Usage: bash ops/scripts/deploy-remote.sh [user@host]
set -euo pipefail

REMOTE="${1:-${MCHAT_DEPLOY_REMOTE:-}}"
REMOTE="${REMOTE:?Set MCHAT_DEPLOY_REMOTE or pass user@host as first argument}"
REMOTE_DIR="${MCHAT_DEPLOY_DIR:-/opt/xiaoxiao/mchat}"
PROJECT_DIR="$(cd "$(dirname "$0")/../.." && pwd)"

echo "==> Build frontend (local)"
cd "$PROJECT_DIR/src/frontend"
npm run build

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

# Preserve existing server .env (JWT, passwords); only bootstrap if missing
if ssh "$REMOTE" "test -f ${REMOTE_DIR}/.env"; then
  echo "==> Keep existing ${REMOTE_DIR}/.env on server"
else
  echo "==> Create initial .env on server"
  JWT_SECRET=$(openssl rand -hex 32)
  ENV_FILE="$PROJECT_DIR/ops/deploy/.env.production.generated"
  cat > "$ENV_FILE" <<EOF
DATABASE_URL=mysql+aiomysql://mchat:CHANGE_ME@localhost:3306/mchat
REDIS_URL=redis://localhost:6379/0

JWT_SECRET=${JWT_SECRET}
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
  rsync -avz "$ENV_FILE" "${REMOTE}:${REMOTE_DIR}/.env"
fi

echo "==> Fix frontend dist permissions on server"
ssh "$REMOTE" "chmod -R a+rX ${REMOTE_DIR}/src/frontend/dist 2>/dev/null || true"

if [ -d "$PROJECT_DIR/skills/mchat-help" ]; then
  echo "==> Sync skills/mchat-help (other server skills untouched)"
  ssh "$REMOTE" "mkdir -p ${REMOTE_DIR}/skills/mchat-help"
  rsync -avz \
    "$PROJECT_DIR/skills/mchat-help/" \
    "${REMOTE}:${REMOTE_DIR}/skills/mchat-help/"
fi

echo "==> Remote setup (pip, db migrate, restart services)"
ssh "$REMOTE" "chmod +x ${REMOTE_DIR}/ops/deploy/remote-setup.sh && bash ${REMOTE_DIR}/ops/deploy/remote-setup.sh"

echo ""
echo "Deployed to ${REMOTE}:${REMOTE_DIR}"
echo "Edit ${REMOTE_DIR}/.env on the server before first use if bootstrap was created."
