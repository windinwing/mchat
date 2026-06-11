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

if [[ -z "$PROJECT_DIR" ]]; then
  MOUNT="${GAMECENTER_MOUNT:-$HOME/mnt/gamecenter-server}"
  OUTER="$MOUNT/newsrc/$SLUG"
  if [[ -d "$OUTER" ]]; then
    PROJECT_DIR="$OUTER"
    for child in "$OUTER"/*; do
      [[ -d "$child" && -f "$child/project.json" || -f "$child/package.json" ]] || continue
      PROJECT_DIR="$child"
      break
    done
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
