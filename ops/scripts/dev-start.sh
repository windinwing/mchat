#!/usr/bin/env bash
# Start backend + frontend for local development.
# Always frees port 3001 first so `make dev` reliably restarts the API.

set -euo pipefail

ROOT="$(cd "$(dirname "$0")/../.." && pwd)"
BACKEND_PORT="${MCHAT_BACKEND_PORT:-3001}"
FRONTEND_PORT="${MCHAT_FRONTEND_PORT:-5173}"
WITH_WORKER="${MCHAT_DEV_WITH_WORKER:-0}"

kill_port() {
  local port=$1
  local pids
  pids=$(lsof -ti:"$port" 2>/dev/null || true)
  if [ -n "$pids" ]; then
    echo "→ Freeing port $port (was PID: $pids)"
    # shellcheck disable=SC2086
    kill -9 $pids 2>/dev/null || true
    sleep 0.3
  fi
}

kill_port "$BACKEND_PORT"
# Vite binds 5173; kill so `make dev` can restart frontend too
kill_port "$FRONTEND_PORT"

bash "$ROOT/ops/scripts/ensure-dev-mysql.sh"

cleanup() {
  if [[ -n "${WORKER_PID:-}" ]] && kill -0 "$WORKER_PID" 2>/dev/null; then
    echo "→ Stopping worker (PID $WORKER_PID)"
    kill "$WORKER_PID" 2>/dev/null || true
  fi
  if [[ -n "${BACKEND_PID:-}" ]] && kill -0 "$BACKEND_PID" 2>/dev/null; then
    echo "→ Stopping backend (PID $BACKEND_PID)"
    kill "$BACKEND_PID" 2>/dev/null || true
  fi
}
trap cleanup EXIT

cd "$ROOT/src/backend"
if [ ! -d venv ]; then
  echo "Missing venv. Run: make install"
  exit 1
fi
# shellcheck disable=SC1091
source venv/bin/activate

echo "→ Starting Core backend http://127.0.0.1:${BACKEND_PORT}"
echo "  (app.main:app — no portal/templates API; use make cloud for those)"
python -m uvicorn app.main:app --reload --host 0.0.0.0 --port "$BACKEND_PORT" &
BACKEND_PID=$!

for i in 1 2 3 4 5 6 7 8 9 10; do
  if curl -sf "http://127.0.0.1:${BACKEND_PORT}/docs" -o /dev/null 2>/dev/null; then
    echo "→ Backend ready (PID $BACKEND_PID)"
    break
  fi
  if ! kill -0 "$BACKEND_PID" 2>/dev/null; then
    echo "Backend exited. Check errors above."
    exit 1
  fi
  if [ "$i" -eq 10 ]; then
    echo "Backend did not respond in time (still starting? PID $BACKEND_PID)"
  fi
  sleep 0.5
done

if [[ "$WITH_WORKER" == "1" ]]; then
  echo "→ Starting worker (enabled for this dev session)"
  WORKER_ENABLED=true python -m app.worker.main &
  WORKER_PID=$!
  echo "→ Worker started (PID $WORKER_PID)"
fi

cd "$ROOT/src/frontend"
if grep -q 'main-portal.tsx' index.html 2>/dev/null; then
  echo "→ Restoring Core index.html (was Cloud entry from deploy/make cloud)"
  cat > index.html <<'HTMLEOF'
<!DOCTYPE html>
<html lang="zh-CN">
  <head>
    <meta charset="UTF-8" />
    <link rel="icon" type="image/svg+xml" href="/vite.svg" />
    <meta name="viewport" content="width=device-width, initial-scale=1.0" />
    <title>MChat</title>
  </head>
  <body class="antialiased">
    <div id="root"></div>
    <script type="module" src="/src/main.tsx"></script>
  </body>
</html>
HTMLEOF
fi
echo "→ Starting frontend (Core edition) http://127.0.0.1:${FRONTEND_PORT}"
echo "  Admin:  http://127.0.0.1:${FRONTEND_PORT}/admin"
echo "  Login:  admin / admin123"
echo "  Cloud:  run make cloud for portal + template marketplace"
export VITE_MCHAT_EDITION=core
npm run dev
