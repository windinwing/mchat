#!/usr/bin/env bash
# Stop local Core dev servers (defaults: backend 3001, frontend 5173).

set -euo pipefail

BACKEND_PORT="${MCHAT_BACKEND_PORT:-3001}"
FRONTEND_PORT="${MCHAT_FRONTEND_PORT:-5173}"

kill_port() {
  local port=$1
  local pids
  pids=$(lsof -ti:"$port" 2>/dev/null || true)
  if [ -n "$pids" ]; then
    echo "Stopping port $port (PID: $pids)"
    # shellcheck disable=SC2086
    kill -9 $pids 2>/dev/null || true
  fi
}

kill_port "$BACKEND_PORT"
kill_port "$FRONTEND_PORT"
echo "Dev servers stopped."
