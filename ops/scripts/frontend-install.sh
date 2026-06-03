#!/usr/bin/env bash
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/../.." && pwd)"
FRONTEND="$ROOT/src/frontend"

bash "$ROOT/ops/scripts/ensure-node20.sh"

cd "$FRONTEND"

if [[ -d node_modules ]] && [[ ! -w node_modules ]]; then
  echo "Removing root-owned node_modules..."
  sudo rm -rf node_modules
fi

install_deps() {
  echo "Installing frontend dependencies (npm install)..."
  rm -rf node_modules
  env -u NODE_ENV npm install
}

if [[ ! -x node_modules/.bin/vite ]]; then
  install_deps
fi

if ! node --input-type=module -e "import('@tailwindcss/vite').then(()=>process.exit(0)).catch(()=>process.exit(1))" 2>/dev/null; then
  echo "Reinstalling frontend dependencies..."
  install_deps
fi

if [[ ! -x node_modules/.bin/vite ]]; then
  echo "vite not installed"
  exit 1
fi

echo "Frontend dependencies ready ($(node -v))"
