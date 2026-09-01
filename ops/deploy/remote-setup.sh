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
echo "==> Validate production security settings"
python -c "from app.application import _validate_production_security; _validate_production_security()"
python -m app.cli db migrate
cd "$DEPLOY_DIR"

echo "==> systemd user service (Core: app.main:app)"
mkdir -p ~/.config/systemd/user
# Core and Cloud bind the same port. A Core deploy must stop the Cloud unit,
# then install and restart only the app.main service.
systemctl --user disable --now mchat-cloud-backend.service 2>/dev/null || true
pkill -f "uvicorn cloud.main:app" 2>/dev/null || true
cp ops/deploy/mchat-backend.service ~/.config/systemd/user/mchat-backend.service
systemctl --user daemon-reload
systemctl --user enable mchat-backend.service
systemctl --user restart mchat-backend.service
sleep 2
if ! systemctl --user is-active mchat-backend.service >/dev/null 2>&1; then
  echo "ERROR: mchat-backend failed to start. Recent logs:"
  journalctl --user -u mchat-backend.service -n 15 --no-pager || true
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
if curl -sf http://127.0.0.1:3001/api/health >/dev/null; then
  echo " backend OK"
else
  echo "ERROR: backend health check failed" >&2
  systemctl --user status mchat-backend.service --no-pager -l || true
  exit 1
fi
if curl -sf -o /dev/null http://127.0.0.1:5180/; then
  echo " frontend OK"
else
  echo "ERROR: frontend health check failed" >&2
  docker logs --tail 30 mchat-frontend 2>/dev/null || true
  exit 1
fi

systemctl --user status mchat-backend.service --no-pager -l || true
echo ""
echo "Done. Check your server URL for /admin and /docs"
