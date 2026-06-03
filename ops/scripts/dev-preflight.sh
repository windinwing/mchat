#!/usr/bin/env bash
# Pre-flight checks before make dev
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/../.." && pwd)"
# shellcheck disable=SC1091
source "$ROOT/ops/scripts/ensure-env.sh"

bash "$ROOT/ops/scripts/ensure-node20.sh"

ensure_docker_env_file
ensure_backend_env_file
sync_backend_database_url

if [[ ! -d "$ROOT/src/backend/venv" ]] || [[ ! -x "$ROOT/src/frontend/node_modules/.bin/vite" ]]; then
  echo "Installing missing dependencies..."
  env -u NODE_ENV make -C "$ROOT" install
else
  bash "$ROOT/ops/scripts/frontend-install.sh" || env -u NODE_ENV make -C "$ROOT" install
fi

if [[ -d "$ROOT/src/frontend/node_modules" ]] && [[ ! -w "$ROOT/src/frontend/node_modules" ]]; then
  echo "node_modules not writable (do not use sudo npm install)"
  echo "  sudo rm -rf src/frontend/node_modules && make install"
  exit 1
fi

if [[ -d "$ROOT/src/backend/venv" ]] && [[ ! -w "$ROOT/src/backend/venv" ]]; then
  echo "venv not writable (do not use sudo make install)"
  echo "  sudo rm -rf src/backend/venv && make install"
  exit 1
fi

bash "$ROOT/ops/scripts/free-dev-ports.sh"
bash "$ROOT/ops/scripts/check-mysql-dev.sh" || true
