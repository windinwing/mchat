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

# Free port 3001 from orphan mchat processes before restarting the service.
# A previous deploy or a manual `uvicorn` run can leave a process holding
# :3001 outside systemd's control (PPID reparented to 1); the service then
# crash-loops on "address already in use". Only kill processes that are
# genuinely mchat (uvicorn + cloud.main/app.main) — never Docker or other
# apps that may also map 3001.
SERVICE_CGROUP=""
if systemctl --user is-active mchat-cloud-backend.service >/dev/null 2>&1; then
  SERVICE_CGROUP="$(systemctl --user show mchat-cloud-backend.service -p ControlGroup --value 2>/dev/null || true)"
fi
for pid in $(ss -tlnpH 2>/dev/null | grep ':3001 ' | grep -oP 'pid=\K[0-9]+' | sort -u); do
  cmd="$(tr '\0' ' ' < /proc/$pid/cmdline 2>/dev/null || true)"
  # Skip anything that is not an mchat uvicorn process.
  case "$cmd" in
    *uvicorn*cloud.main:app*|*uvicorn*app.main:app*) : ;;  # mchat backend
    *) echo "    Keeping non-mchat :3001 holder pid=$pid ($cmd)"; continue ;;
  esac
  # Skip the process if it belongs to this very service (let systemd manage it).
  if [ -n "$SERVICE_CGROUP" ]; then
    if grep -q "$SERVICE_CGROUP" /proc/$pid/cgroup 2>/dev/null; then
      echo "    Keeping :3001 holder pid=$pid (managed by mchat-cloud-backend.service)"
      continue
    fi
  fi
  echo "    Killing orphan mchat :3001 holder pid=$pid"
  kill "$pid" 2>/dev/null || true
done
# Wait briefly for the port to release, then force-kill any stragglers.
sleep 3
for pid in $(ss -tlnpH 2>/dev/null | grep ':3001 ' | grep -oP 'pid=\K[0-9]+' | sort -u); do
  cmd="$(tr '\0' ' ' < /proc/$pid/cmdline 2>/dev/null || true)"
  case "$cmd" in
    *uvicorn*cloud.main:app*|*uvicorn*app.main:app*) : ;;
    *) continue ;;
  esac
  if [ -n "$SERVICE_CGROUP" ] && grep -q "$SERVICE_CGROUP" /proc/$pid/cgroup 2>/dev/null; then
    continue
  fi
  echo "    Force-killing orphan mchat :3001 holder pid=$pid"
  kill -9 "$pid" 2>/dev/null || true
done

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

echo "==> Build worker service (DevBridge compile queue)"
# Kill any orphan build-worker processes not managed by systemd before
# restarting the service. A stale worker (left by a manual launch or a previous
# deploy) would otherwise race with the service pool on the same Redis queue.
# The worker holds a Redis singleton lock, so duplicates exit on their own — but
# killing them avoids the wasted startup.
#
# Match only the python interpreter running the worker script. Do NOT use a
# bare `pgrep -f gamecenter-build-worker.py`: this very script's command line
# contains that string, so it would match (and kill) itself.
WORKER_CGROUP=""
if systemctl --user is-active mchat-build-worker.service >/dev/null 2>&1; then
  WORKER_CGROUP="$(systemctl --user show mchat-build-worker.service -p ControlGroup --value 2>/dev/null || true)"
fi
_kill_orphan_workers() {
  for pid in $(pgrep -f "gamecenter-build-worker\.py" 2>/dev/null | sort -u); do
    # Only act on actual python processes running the worker. pgrep -f matches
    # this script's own command line (which contains the worker filename), so
    # verify the executable is a python interpreter before killing.
    exe="$(readlink /proc/$pid/exe 2>/dev/null || true)"
    case "$exe" in
      */python*|*/python3*) : ;;
      *) continue ;;  # bash wrapper / this script itself — skip
    esac
    # Skip the systemd-managed pool (let the service restart handle it).
    if [ -n "$WORKER_CGROUP" ] && grep -q "$WORKER_CGROUP" /proc/$pid/cgroup 2>/dev/null; then
      echo "    Keeping worker pid=$pid (managed by mchat-build-worker.service)"
      continue
    fi
    echo "    $1 orphan build worker pid=$pid"
    $2 "$pid" 2>/dev/null || true
  done
}
_kill_orphan_workers "Killing"      kill
sleep 2
_kill_orphan_workers "Force-killing" "kill -9"

cp ops/deploy/mchat-build-worker.service ~/.config/systemd/user/mchat-build-worker.service
systemctl --user daemon-reload
systemctl --user enable mchat-build-worker.service
systemctl --user restart mchat-build-worker.service

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
