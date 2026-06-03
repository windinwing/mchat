#!/usr/bin/env bash
# First-time setup: git pull && make setup && make dev
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/../.." && pwd)"
cd "$ROOT"
# shellcheck disable=SC1091
source "$ROOT/ops/scripts/ensure-env.sh"

COMPOSE_LITE=(ops/docker/docker-compose.lite.yml)
COMPOSE_ENV=(--env-file ops/docker/.env)
SETUP_MYSQL="${MCHAT_SETUP_MYSQL:-1}"

echo "mchat dev setup (lite MySQL)"

check_command() {
  command -v "$1" &>/dev/null || { echo "Missing dependency: $1"; exit 1; }
}

echo ""
echo "Checking dependencies..."
check_command python3
check_command node
check_command npm
bash "$ROOT/ops/scripts/ensure-node20.sh"
[[ "$SETUP_MYSQL" == "1" ]] && check_command docker

python3 -m venv /tmp/mchat-venv-check 2>/dev/null || { echo "python3 -m venv unavailable"; exit 1; }
rm -rf /tmp/mchat-venv-check

configure_docker_cmd

echo "Python $(python3 -V 2>&1 | awk '{print $2}')"
echo "Node $(node -v)"
echo "npm $(npm -v)"

echo ""
echo "Configuring environment..."
ensure_docker_env_file
ensure_backend_env_file
fix_env_permissions
read_mysql_env
sync_backend_database_url
echo "DATABASE_URL -> localhost:${MYSQL_PORT} (${MYSQL_USER} / ${MYSQL_DATABASE})"

if docker ps --format '{{.Names}}' 2>/dev/null | grep -q '^mchat-dev-mysql$'; then
  echo "Note: legacy container mchat-dev-mysql on 3306; lite uses port ${MYSQL_PORT}. Consider: docker rm -f mchat-dev-mysql"
fi

if [[ "$SETUP_MYSQL" == "1" ]]; then
  echo ""
  echo "Starting lite MySQL (host port ${MYSQL_PORT})..."
  docker_compose -f "${COMPOSE_LITE[@]}" "${COMPOSE_ENV[@]}" up -d mysql

  echo "Waiting for MySQL..."
  for _ in $(seq 1 30); do
    docker_compose -f "${COMPOSE_LITE[@]}" "${COMPOSE_ENV[@]}" exec -T mysql \
      mysqladmin ping -h localhost -u root -p"${MYSQL_ROOT_PASSWORD}" --silent 2>/dev/null && break
    sleep 2
  done

  mysql_auth_ok() {
    docker_compose -f "${COMPOSE_LITE[@]}" "${COMPOSE_ENV[@]}" exec -T mysql \
      mysql -u"$MYSQL_USER" -p"$MYSQL_PASSWORD" -e "SELECT 1" "$MYSQL_DATABASE" >/dev/null 2>&1
  }
  if mysql_auth_ok; then
    echo "MySQL ready (localhost:${MYSQL_PORT})"
  else
    echo "MySQL password mismatch; recreating volume..."
    docker_compose -f "${COMPOSE_LITE[@]}" "${COMPOSE_ENV[@]}" down -v
    docker_compose -f "${COMPOSE_LITE[@]}" "${COMPOSE_ENV[@]}" up -d mysql
    for _ in $(seq 1 30); do mysql_auth_ok && break; sleep 2; done
    mysql_auth_ok && echo "MySQL recreated with ops/docker/.env credentials" || echo "MySQL still unreachable; check ops/docker/.env"
  fi
fi

echo ""
echo "Installing dependencies..."
fix_install_permissions
env -u NODE_ENV make install

echo ""
echo "Initializing database..."
if [[ "$SETUP_MYSQL" == "1" ]]; then
  bash "$ROOT/ops/scripts/verify-mysql.sh" || exit 1
  make db-init || { echo "db-init failed; run: make db-docker-reset-lite && make setup"; exit 1; }
else
  echo "Skipped db-init (MCHAT_SETUP_MYSQL=0)"
fi

echo ""
echo "============================================"
echo "Setup complete. Next: make dev"
echo "MySQL: localhost:${MYSQL_PORT}  user: ${MYSQL_USER} / ${MYSQL_PASSWORD}"
echo "Docker stack: make docker-up-lite"
echo "============================================"
