#!/bin/bash
# Deploy mchat Cloud (Core + signup/portal/templates) to remote server.
# Usage: bash ops/scripts/deploy-remote-cloud.sh
set -euo pipefail

REMOTE="${1:-${MCHAT_DEPLOY_REMOTE:-}}"
REMOTE="${REMOTE:?Set MCHAT_DEPLOY_REMOTE or pass user@host as first argument}"
REMOTE_DIR="${MCHAT_DEPLOY_DIR:-/opt/xiaoxiao/mchat}"
PROJECT_DIR="$(cd "$(dirname "$0")/../.." && pwd)"

echo "==> Build frontend (Cloud edition)"
cd "$PROJECT_DIR/src/frontend"
INDEX_BAK="$(mktemp)"
cp index.html "$INDEX_BAK"
trap 'mv -f "$INDEX_BAK" index.html 2>/dev/null || true' EXIT
cat > index.html <<'HTMLEOF'
<!DOCTYPE html>
<html lang="zh-CN">
  <head>
    <meta charset="UTF-8" />
    <link rel="icon" type="image/svg+xml" href="/vite.svg" />
    <meta name="viewport" content="width=device-width, initial-scale=1.0" />
    <title>MChat Cloud</title>
  </head>
  <body class="antialiased">
    <div id="root"></div>
    <script type="module" src="/src/main-portal.tsx"></script>
  </body>
</html>
HTMLEOF
VITE_MCHAT_EDITION=cloud npm run build:cloud
mv -f "$INDEX_BAK" index.html
trap - EXIT
# widget-loader.js lives in public/; ensure it is in dist for Docker nginx
cp -f public/widget-loader.js dist/widget-loader.js
chmod a+r dist/widget-loader.js public/widget-loader.js 2>/dev/null || true

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
  --exclude 'data' \
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
  cat > "$ENV_FILE" <<'EOF'
DATABASE_URL=mysql+aiomysql://mchat:CHANGE_ME@localhost:3306/mchat
REDIS_URL=redis://localhost:6379/0

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
for patent_dir in "$PROJECT_DIR"/skills/patent-*; do
  [ -d "$patent_dir" ] || continue
  sync_skill_dir "$(basename "$patent_dir")"
done

echo "==> Remote setup (pip, db migrate, restart Cloud services)"
ssh "$REMOTE" "chmod +x ${REMOTE_DIR}/ops/deploy/remote-setup-cloud.sh && bash ${REMOTE_DIR}/ops/deploy/remote-setup-cloud.sh"

echo "==> Fix frontend dist permissions again (after Docker restart)"
ssh "$REMOTE" "chmod -R a+rX ${REMOTE_DIR}/src/frontend/dist ${REMOTE_DIR}/src/frontend/public 2>/dev/null || true"

echo ""
echo "Cloud deployed to https://mchat.9235.net"
echo "  Admin:    https://mchat.9235.net/admin"
echo "  Portal:   https://mchat.9235.net/portal"
echo "  API docs: https://mchat.9235.net/docs"
echo "  Register: https://mchat.9235.net/register"
