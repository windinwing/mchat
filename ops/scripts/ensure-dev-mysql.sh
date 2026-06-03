#!/usr/bin/env bash
# Ensure local dev MySQL is reachable (start docker compose lite if needed).
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/../.." && pwd)"
# shellcheck disable=SC1091
source "$ROOT/ops/scripts/ensure-env.sh"

COMPOSE_FILE=ops/docker/docker-compose.lite.yml
ENV_FILE=ops/docker/.env
MAX_WAIT="${MCHAT_MYSQL_WAIT_SEC:-60}"

ensure_docker_env_file 2>/dev/null || true
read_mysql_env

HOST="${MCHAT_MYSQL_HOST:-127.0.0.1}"
PORT="${MCHAT_MYSQL_PORT:-$MYSQL_PORT}"

mysql_ready() {
  if command -v nc >/dev/null 2>&1; then
    nc -z "$HOST" "$PORT" 2>/dev/null
    return $?
  fi
  (echo >/dev/tcp/"$HOST"/"$PORT") >/dev/null 2>&1
}

wait_mysql() {
  local i=0
  while [ "$i" -lt "$MAX_WAIT" ]; do
    if mysql_ready; then
      return 0
    fi
    sleep 1
    i=$((i + 1))
  done
  return 1
}

if mysql_ready; then
  echo "→ MySQL already listening on ${HOST}:${PORT}"
  exit 0
fi

if ! command -v docker >/dev/null 2>&1; then
  echo "ERROR: MySQL not available on ${HOST}:${PORT} and Docker is not installed."
  echo "  Start MySQL manually, or install Docker and run:"
  echo "  docker compose -f ops/docker/docker-compose.lite.yml --env-file ops/docker/.env up -d mysql"
  exit 1
fi

echo "→ Starting dev MySQL (docker compose)…"
docker_compose -f "$COMPOSE_FILE" --env-file "$ENV_FILE" up -d mysql

echo "→ Waiting for MySQL on ${HOST}:${PORT} (up to ${MAX_WAIT}s)…"
if ! wait_mysql; then
  echo "ERROR: MySQL did not become ready. Check: docker logs mchat-mysql"
  exit 1
fi
echo "→ MySQL ready"
