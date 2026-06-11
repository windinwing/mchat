#!/usr/bin/env bash
# Resolve a GameCenter project slug and run the fixed bridge build script.
# Usage (on server): gamecenter-remote-build.sh <project_slug> [--force]
# Usage (from Mac):  ops/scripts/gamecenter-ssh-build.sh 10.98.8.15 <project_slug> [--force]
set -euo pipefail

SLUG="${1:-}"
FORCE_FLAG=""
if [[ "${2:-}" == "--force" ]]; then
  FORCE_FLAG="--force"
  export GAMECENTER_FORCE_REBUILD=1
fi

if [[ -z "$SLUG" ]]; then
  echo "usage: $0 <project_slug> [--force]" >&2
  exit 1
fi

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "$SCRIPT_DIR/../.." && pwd)"
BACKEND_DIR="$REPO_ROOT/src/backend"
RESOLVER="$SCRIPT_DIR/resolve-gamecenter-project.py"

if [[ ! -d "$BACKEND_DIR" ]]; then
  echo "backend dir not found: $BACKEND_DIR" >&2
  exit 1
fi

resolve_with_venv() {
  local py="$BACKEND_DIR/venv/bin/python"
  [[ -x "$py" ]] || return 1
  (
    cd "$BACKEND_DIR"
    if [[ -f .env ]]; then
      set -a
      # shellcheck disable=SC1091
      source .env
      set +a
    fi
    export PYTHONPATH="$BACKEND_DIR"
    export BACKEND_DIR
    "$py" - <<PY
import os
import sys

sys.path.insert(0, os.environ["BACKEND_DIR"])

from app.services.gamecenter_provider import create_gamecenter_bridge_service

slug = ${SLUG@Q}
svc = create_gamecenter_bridge_service()
for project in svc.list_projects():
    if project.slug == slug:
        print(project.path)
        raise SystemExit(0)
raise SystemExit(f"project slug not found: {slug}")
PY
  )
}

resolve_with_stdlib() {
  python3 "$RESOLVER" "$REPO_ROOT" "$SLUG"
}

load_cocos_bin() {
  local bin=""
  bin="$(python3 "$RESOLVER" "$REPO_ROOT" --print-cocos-bin 2>/dev/null || true)"
  if [[ -n "$bin" && -x "$bin" ]]; then
    export GAMECENTER_COCOS_CREATOR_BIN="$bin"
    echo "Using Cocos from admin settings: $bin"
    return 0
  fi
  if [[ -n "${GAMECENTER_COCOS_CREATOR_BIN:-}" && -x "${GAMECENTER_COCOS_CREATOR_BIN}" ]]; then
    echo "Using Cocos from environment: $GAMECENTER_COCOS_CREATOR_BIN"
    return 0
  fi
  echo "Cocos Creator not configured (cocos_creator_bin empty or not executable on server)" >&2
  return 1
}

PROJECT_DIR=""
RESOLVE_ERR="$(mktemp)"
trap 'rm -f "$RESOLVE_ERR"' EXIT

if PROJECT_DIR="$(resolve_with_venv 2>"$RESOLVE_ERR")"; then
  :
elif PROJECT_DIR="$(resolve_with_stdlib 2>"$RESOLVE_ERR")"; then
  if [[ -s "$RESOLVE_ERR" ]]; then
    echo "venv resolver note: $(head -1 "$RESOLVE_ERR")" >&2
  fi
  echo "Note: used stdlib project resolver" >&2
else
  echo "Failed to resolve project slug: $SLUG" >&2
  if [[ -s "$RESOLVE_ERR" ]]; then
    cat "$RESOLVE_ERR" >&2
  fi
  echo "Hint: copy slug exactly from DevBridge UI (e.g. pkg0002-3-x-3-8-3ts, not pkg0002-3-x-3-8-8-3ts)" >&2
  exit 1
fi

load_cocos_bin || true

echo "Building slug=$SLUG at $PROJECT_DIR"
bash "$SCRIPT_DIR/gamecenter-bridge-build.sh" "$PROJECT_DIR" $FORCE_FLAG
