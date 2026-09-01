#!/usr/bin/env bash
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/../.." && pwd)"
BACKEND_PORT="${MCHAT_BACKEND_PORT:-3001}"
FRONTEND_PORT="${MCHAT_FRONTEND_PORT:-5173}"
WITH_WORKER="${MCHAT_DEV_WITH_WORKER:-0}"

bash "$ROOT/ops/scripts/dev-preflight.sh"

# shellcheck disable=SC1091
source "$ROOT/ops/scripts/ensure-env.sh"
ensure_docker_env_file 2>/dev/null || true
sync_backend_database_url 2>/dev/null || true
bash "$ROOT/ops/scripts/ensure-dev-mysql.sh"
bash "$ROOT/ops/scripts/verify-mysql.sh" || exit 1

bash "$ROOT/ops/scripts/ensure-dev-mysql.sh"

cleanup() {
  [[ -n "${WORKER_PID:-}" ]] && kill -0 "$WORKER_PID" 2>/dev/null && kill "$WORKER_PID" 2>/dev/null || true
  [[ -n "${BACKEND_PID:-}" ]] && kill -0 "$BACKEND_PID" 2>/dev/null && kill "$BACKEND_PID" 2>/dev/null || true
}
trap cleanup EXIT

cd "$ROOT/src/backend"
# shellcheck disable=SC1091
source venv/bin/activate

lan_ip=$(hostname -I 2>/dev/null | awk '{print $1}' || true)

echo "Starting Core backend http://0.0.0.0:${BACKEND_PORT}"
python -m uvicorn app.main:app --reload --host 0.0.0.0 --port "$BACKEND_PORT" &
BACKEND_PID=$!

for i in $(seq 1 20); do
  curl -sf "http://127.0.0.1:${BACKEND_PORT}/docs" -o /dev/null 2>/dev/null && break
  kill -0 "$BACKEND_PID" 2>/dev/null || { echo "Backend exited."; exit 1; }
  [[ "$i" -eq 20 ]] && echo "Backend slow to start (PID $BACKEND_PID)"
  sleep 0.5
done
echo "Backend ready (PID $BACKEND_PID)"

if [[ "$WITH_WORKER" == "1" ]]; then
  WORKER_ENABLED=true python -m app.worker.main &
  WORKER_PID=$!
fi

cd "$ROOT/src/frontend"
echo "Starting frontend http://0.0.0.0:${FRONTEND_PORT}"
[[ -n "$lan_ip" ]] && echo "  Open: http://${lan_ip}:${FRONTEND_PORT}/chat  (admin / admin123, 顶部可切到管理)"
export VITE_MCHAT_EDITION=core
export VITE_BACKEND_PROXY_TARGET="${VITE_BACKEND_PROXY_TARGET:-http://127.0.0.1:${BACKEND_PORT}}"
exec env -u NODE_ENV npm run dev
