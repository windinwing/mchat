#!/usr/bin/env bash
# Start Cloud backend + frontend for local development.
# Cloud = Core + signup, portal API, template marketplace.
# Always frees port 3001 first so `make cloud` reliably restarts the API.

set -euo pipefail

ROOT="$(cd "$(dirname "$0")/../.." && pwd)"
BACKEND_PORT="${MCHAT_BACKEND_PORT:-3001}"
FRONTEND_PORT="${MCHAT_FRONTEND_PORT:-5173}"

kill_port() {
  local port=$1
  local pids
  pids=$(lsof -ti:"$port" 2>/dev/null || true)
  if [ -n "$pids" ]; then
    echo "→ Freeing port $port (was PID: $pids)"
    kill -9 $pids 2>/dev/null || true
    sleep 0.3
  fi
}

cleanup() {
  echo ""
  echo "→ Restoring index.html (Core entry)"
  if [ -f "$ROOT/src/frontend/index.html.bak" ]; then
    mv "$ROOT/src/frontend/index.html.bak" "$ROOT/src/frontend/index.html"
  fi
}
trap cleanup EXIT

kill_port "$BACKEND_PORT"
kill_port "$FRONTEND_PORT"

bash "$ROOT/ops/scripts/dev-preflight.sh"

# shellcheck disable=SC1091
source "$ROOT/ops/scripts/ensure-env.sh"
ensure_docker_env_file 2>/dev/null || true
sync_backend_database_url 2>/dev/null || true
bash "$ROOT/ops/scripts/ensure-dev-mysql.sh"
bash "$ROOT/ops/scripts/verify-mysql.sh" || exit 1

# ---- Backend (Cloud: cloud.main:app) ----
cd "$ROOT/src/backend"
if [ ! -d venv ]; then
  echo "Missing venv. Run: make install"
  exit 1
fi
source venv/bin/activate

echo "→ Starting Cloud backend http://127.0.0.1:${BACKEND_PORT}"
echo "  (cloud.main:app = Core + signup + portal + templates)"
python -m uvicorn cloud.main:app --reload --host 0.0.0.0 --port "$BACKEND_PORT" &
BACKEND_PID=$!

for i in 1 2 3 4 5 6 7 8 9 10; do
  if curl -sf "http://127.0.0.1:${BACKEND_PORT}/docs" -o /dev/null 2>/dev/null; then
    echo "→ Cloud backend ready (PID $BACKEND_PID)"
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

# ---- Frontend (swap index.html so SPA fallback loads Cloud app) ----
cd "$ROOT/src/frontend"
echo "→ Swapping index.html → Cloud entry (main-portal.tsx)"
cp index.html index.html.bak
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

echo "→ Starting frontend (Cloud edition) http://127.0.0.1:${FRONTEND_PORT}"
echo "  Admin:     http://127.0.0.1:${FRONTEND_PORT}/admin"
echo "  Portal:    http://127.0.0.1:${FRONTEND_PORT}/portal/dashboard"
echo "  Templates: http://127.0.0.1:${FRONTEND_PORT}/portal/templates"
echo "  Register:  http://127.0.0.1:${FRONTEND_PORT}/register"
echo "  Login:     admin / admin123"
export VITE_MCHAT_EDITION=cloud
exec npm run dev
