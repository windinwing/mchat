#!/usr/bin/env bash
# Free ports for make dev; stop Docker lite frontend/backend if needed
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/../.." && pwd)"
BACKEND_PORT="${MCHAT_BACKEND_PORT:-3001}"
FRONTEND_PORT="${MCHAT_FRONTEND_PORT:-5173}"

# shellcheck disable=SC1091
source "$ROOT/ops/scripts/ensure-env.sh"

kill_port() {
  local port=$1
  local pids
  pids=$(lsof -ti:"$port" 2>/dev/null || true)
  if [[ -n "$pids" ]]; then
    echo "Freeing port $port (PID: $pids)"
    # shellcheck disable=SC2086
    kill -9 $pids 2>/dev/null || true
    sleep 0.3
  fi
}

stop_docker_dev_containers() {
  configure_docker_cmd
  if [[ -n "${MCHAT_DOCKER:-}" ]]; then
    # shellcheck disable=SC2086
    ${MCHAT_DOCKER} stop mchat-frontend mchat-backend 2>/dev/null && echo "Stopped Docker frontend/backend (MySQL kept)" || true
  else
    docker stop mchat-frontend mchat-backend 2>/dev/null && echo "Stopped Docker frontend/backend (MySQL kept)" || true
  fi
}

kill_port "$BACKEND_PORT"

if lsof -ti:"$FRONTEND_PORT" >/dev/null 2>&1; then
  stop_docker_dev_containers
fi
kill_port "$FRONTEND_PORT"

if lsof -ti:"$FRONTEND_PORT" >/dev/null 2>&1; then
  echo "Port ${FRONTEND_PORT} still in use."
  echo "  sudo docker stop mchat-frontend mchat-backend"
  echo "  or use: make docker-up-lite"
  exit 1
fi
