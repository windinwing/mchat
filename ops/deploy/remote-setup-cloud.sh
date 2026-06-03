#!/bin/bash
# Run on Cloud server after rsync: bash /opt/xiaoxiao/mchat/ops/deploy/remote-setup-cloud.sh
# Cloud = Core + signup + portal API + template marketplace
set -euo pipefail

DEPLOY_DIR="/opt/xiaoxiao/mchat"
cd "$DEPLOY_DIR"

echo "==> Python venv & dependencies"
python3 -m venv src/backend/venv
source src/backend/venv/bin/activate
pip install -q --upgrade pip
pip install -q -r src/backend/requirements-lite.txt

mkdir -p data/uploads logs
chmod 755 data data/uploads
chmod -R a+rX src/frontend/dist 2>/dev/null || true

ln -sf "$DEPLOY_DIR/.env" src/backend/.env

echo "==> Database migrate"
cd src/backend
set -a && source .env && set +a
python -m app.cli db migrate
cd "$DEPLOY_DIR"

echo "==> systemd user service (Cloud: cloud.main:app)"
# Stop legacy Core-only unit if present — it also binds :3001 and blocks Cloud routes.
if systemctl --user is-active mchat-backend.service >/dev/null 2>&1; then
  echo "    Stopping mchat-backend.service (Core) to free port 3001"
  systemctl --user stop mchat-backend.service
fi
systemctl --user disable mchat-backend.service 2>/dev/null || true

mkdir -p ~/.config/systemd/user
cp ops/deploy/mchat-cloud-backend.service ~/.config/systemd/user/mchat-cloud-backend.service
systemctl --user daemon-reload
systemctl --user enable mchat-cloud-backend.service
systemctl --user restart mchat-cloud-backend.service
sleep 2
if ! systemctl --user is-active mchat-cloud-backend.service >/dev/null 2>&1; then
  echo "ERROR: mchat-cloud-backend failed to start. Recent logs:"
  journalctl --user -u mchat-cloud-backend.service -n 15 --no-pager || true
  exit 1
fi

if command -v loginctl >/dev/null 2>&1; then
  loginctl enable-linger "$USER" 2>/dev/null || true
fi

echo "==> Frontend nginx (Docker, port 5180)"
docker stop mchat-frontend 2>/dev/null || true
docker rm mchat-frontend 2>/dev/null || true
docker run -d --name mchat-frontend --restart unless-stopped \
  -p 5180:80 \
  -v "$DEPLOY_DIR/src/frontend/dist:/usr/share/nginx/html:ro" \
  -v "$DEPLOY_DIR/ops/deploy/nginx-mchat.conf:/etc/nginx/conf.d/default.conf:ro" \
  --add-host=host.docker.internal:host-gateway \
  nginx:alpine

sleep 3
echo "==> Health check"
curl -sf http://127.0.0.1:3001/api/health && echo " backend OK" || echo " backend FAILED"
curl -sf http://127.0.0.1:3001/api/templates | python3 -c "import sys,json; d=json.load(sys.stdin); print(f'  templates: {len(d)}')" 2>/dev/null || echo "  templates: N/A"
curl -sf -o /dev/null -w "%{http_code}\n" http://127.0.0.1:5180/ | grep -q 200 && echo " frontend OK" || echo " frontend check"

echo ""
echo "Cloud service running."
echo "  Web:    https://mchat.9235.net"
echo "  Portal: https://mchat.9235.net/portal"
echo "  API docs: /docs on your SERVER_HOST:SERVER_PORT"
