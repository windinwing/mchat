#!/usr/bin/env bash
# Docker lite one-shot: .env + MySQL password fix + build
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/../.." && pwd)"
cd "$ROOT"
# shellcheck disable=SC1091
source "$ROOT/ops/scripts/ensure-env.sh"

COMPOSE_FILE=ops/docker/docker-compose.lite.yml
ENV_FILE=ops/docker/.env

configure_docker_cmd
ensure_docker_env_file
ensure_backend_env_file
fix_env_permissions
read_mysql_env

mysql_auth_ok() {
  docker_compose -f "$COMPOSE_FILE" --env-file "$ENV_FILE" exec -T mysql \
    mysql -u"$MYSQL_USER" -p"$MYSQL_PASSWORD" -e "SELECT 1" "$MYSQL_DATABASE" >/dev/null 2>&1
}

ensure_backend_env_file
sync_backend_database_url
echo "Synced src/backend/.env"

echo "Starting MySQL..."
docker_compose -f "$COMPOSE_FILE" --env-file "$ENV_FILE" up -d mysql

for _ in $(seq 1 30); do
  docker_compose -f "$COMPOSE_FILE" --env-file "$ENV_FILE" exec -T mysql \
    mysqladmin ping -h localhost -u root -p"$MYSQL_ROOT_PASSWORD" --silent 2>/dev/null && break
  sleep 2
done

if mysql_auth_ok; then
  echo "MySQL credentials OK"
else
  echo "MySQL password mismatch; recreating volume..."
  docker_compose -f "$COMPOSE_FILE" --env-file "$ENV_FILE" down -v
  docker_compose -f "$COMPOSE_FILE" --env-file "$ENV_FILE" up -d mysql
  for _ in $(seq 1 30); do mysql_auth_ok && break; sleep 2; done
fi

echo "Building and starting backend + frontend..."
docker_compose -f "$COMPOSE_FILE" --env-file "$ENV_FILE" up -d --build

LAN=$(hostname -I 2>/dev/null | awk '{print $1}')
echo ""
echo "Docker lite is up"
echo "  Frontend: http://${LAN:-localhost}:${FRONTEND_PORT}/admin"
echo "  Backend:  http://${LAN:-localhost}:${BACKEND_PORT}/docs"
echo "  Login:    ${ADMIN_USERNAME} / ${ADMIN_PASSWORD}"

fix_install_permissions 2>/dev/null || true
