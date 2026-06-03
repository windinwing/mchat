#!/usr/bin/env bash
# Wipe Docker lite + local deps for a clean make setup / make docker-up-lite
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/../.." && pwd)"
cd "$ROOT"

if [[ "${MCHAT_RESET_FORCE:-}" != "1" ]]; then
  echo "This will remove:"
  echo "  - Docker lite containers, volumes, local images"
  echo "  - src/backend/venv, src/backend/.env"
  echo "  - src/frontend/node_modules, dist"
  echo "  - ops/docker/.env"
  echo ""
  read -r -p "Continue? [y/N] " ans
  [[ "$ans" =~ ^[Yy]$ ]] || { echo "Cancelled"; exit 0; }
fi

echo "Stopping dev processes..."
bash "$ROOT/ops/scripts/dev-stop.sh" 2>/dev/null || true

if [[ -f ops/scripts/docker-compose-cmd.sh ]]; then
  DC=(bash ops/scripts/docker-compose-cmd.sh)
elif docker info >/dev/null 2>&1; then
  DC=(docker compose)
else
  DC=(sudo docker compose)
fi

ENV_FILE=ops/docker/.env
COMPOSE=(ops/docker/docker-compose.lite.yml)

echo "Stopping Docker lite (including MySQL volume)..."
if [[ -f "$ENV_FILE" ]]; then
  "${DC[@]}" -f "${COMPOSE[@]}" --env-file "$ENV_FILE" down -v --remove-orphans 2>/dev/null || true
else
  "${DC[@]}" -f "${COMPOSE[@]}" down -v --remove-orphans 2>/dev/null || true
fi

for name in mchat-mysql mchat-backend mchat-frontend mchat-dev-mysql; do
  sudo docker rm -f "$name" 2>/dev/null || docker rm -f "$name" 2>/dev/null || true
done

echo "Removing local deps and config..."
rm_own() {
  local path=$1
  [[ -e "$path" || -L "$path" ]] || return 0
  rm -rf "$path" 2>/dev/null || sudo rm -rf "$path"
}

rm_own src/backend/venv
rm_own src/frontend/node_modules
rm_own src/frontend/dist
rm -f src/backend/.env ops/docker/.env

echo ""
echo "Reset complete. Next:"
echo "  make setup && make dev"
echo "  or: make docker-up-lite"
