#!/bin/bash
# Run on server after rsync: bash /opt/xiaoxiao/mchat/ops/deploy/remote-setup.sh
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

echo "==> systemd user service"
mkdir -p ~/.config/systemd/user
cp ops/deploy/mchat-backend.service ~/.config/systemd/user/mchat-backend.service
systemctl --user daemon-reload
systemctl --user enable mchat-backend.service
systemctl --user restart mchat-backend.service

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
curl -sf -o /dev/null -w "%{http_code}\n" http://127.0.0.1:5180/ | grep -q 200 && echo " frontend OK" || echo " frontend check"

systemctl --user status mchat-backend.service --no-pager -l || true
echo ""
echo "Done. Check your server URL for /admin and /docs"
