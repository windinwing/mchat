#!/usr/bin/env bash
# Run a command inside src/backend venv (source activate when available).
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/../.." && pwd)"
BACKEND="$ROOT/src/backend"

if [[ ! -f "$BACKEND/venv/bin/activate" ]]; then
  echo "Missing venv. Run: make install" >&2
  exit 1
fi

cd "$BACKEND"
# shellcheck disable=SC1091
source venv/bin/activate
exec "$@"
