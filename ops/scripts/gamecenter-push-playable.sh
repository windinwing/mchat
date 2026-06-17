#!/usr/bin/env bash
# Upload local build/web-mobile to server playables (after local compile on mounted tree).
# Usage: gamecenter-push-playable.sh [ssh_host] <slug> [project_dir]
set -euo pipefail

HOST_RAW="${1:-10.98.8.15}"
SLUG="${2:-}"
PROJECT_DIR="${3:-}"
SSH_USER="${SSH_USER:-xiaoxiao}"
if [[ "$HOST_RAW" == *@* ]]; then
  RSYNC_HOST="$HOST_RAW"
else
  RSYNC_HOST="${SSH_USER}@${HOST_RAW}"
fi
REMOTE_PLAYABLES="${REMOTE_PLAYABLES_ROOT:-/opt/xiaoxiao/gamecenter/playables}"

if [[ -z "$SLUG" ]]; then
  echo "usage: $0 [ssh_host] <slug> [project_dir]" >&2
  echo "  project_dir: local path with build/web-mobile (default: resolve via mount + slug)" >&2
  exit 1
fi

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
# shellcheck disable=SC1091
source "$SCRIPT_DIR/gamecenter-lib.sh"

if [[ -z "$PROJECT_DIR" ]]; then
  MOUNT="${GAMECENTER_MOUNT:-$HOME/mnt/gamecenter-server}"
  # GameCenter post-restructure: src/<category>/<slug>/ (e.g. src/misc/cat/).
  # Try to resolve source_relpath from the xcx workspace; fall back to src/<slug>/.
  source_relpath="$(gc_local_source_relpath "$SLUG" 2>/dev/null || true)"
  if [[ -n "$source_relpath" ]]; then
    OUTER="$MOUNT/src/$source_relpath"
  else
    OUTER="$MOUNT/src/$SLUG"
  fi
  if [[ -d "$OUTER" ]]; then
    PROJECT_DIR="$(gc_resolve_nested_project_dir "$OUTER")"
  fi
fi

BUILD_OUT="${PROJECT_DIR}/build/web-mobile"
if [[ ! -d "$BUILD_OUT" || -z "$(ls -A "$BUILD_OUT" 2>/dev/null || true)" ]]; then
  echo "build/web-mobile missing or empty: $BUILD_OUT" >&2
  echo "Run gamecenter-local-build-project.sh first." >&2
  exit 1
fi

DEST="${REMOTE_PLAYABLES}/${SLUG}/"
echo "Pushing $BUILD_OUT -> ${RSYNC_HOST}:${DEST}"
rsync -avz --delete "$BUILD_OUT/" "${RSYNC_HOST}:${DEST}"

echo "Playable files synced. Publish current release in DevBridge UI if needed."
echo "Or trigger publish API on server for slug=$SLUG"
PLAY_PATH="$(gc_play_path "$SLUG")"
echo "Playable URL: http://${HOST_RAW#*@}:5099${PLAY_PATH}"
