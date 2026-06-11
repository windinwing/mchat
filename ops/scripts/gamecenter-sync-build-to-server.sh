#!/usr/bin/env bash
# Push local build/web-mobile + sources back to server.
# GameCenter :5099 serves from <project>/build/web-mobile (NOT playables/).
# Usage: gamecenter-sync-build-to-server.sh [ssh_host] <slug> [local_project_dir]
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
# shellcheck disable=SC1091
source "$SCRIPT_DIR/gamecenter-lib.sh"
if [[ -f "$SCRIPT_DIR/gamecenter-local.env" ]]; then
  # shellcheck disable=SC1091
  source "$SCRIPT_DIR/gamecenter-local.env"
fi

HOST_RAW="${1:-10.98.8.15}"
SLUG="${2:-}"
PROJECT_DIR="${3:-}"
SSH_USER="${SSH_USER:-xiaoxiao}"
if [[ "$HOST_RAW" == *@* ]]; then
  RSYNC_HOST="$HOST_RAW"
  HOST_IP="${HOST_RAW#*@}"
else
  RSYNC_HOST="${SSH_USER}@${HOST_RAW}"
  HOST_IP="$HOST_RAW"
fi
REMOTE_ROOT="${REMOTE_GAMECENTER_ROOT:-/opt/xiaoxiao/gamecenter}"
REMOTE_PARENT="${REMOTE_PROJECT_PARENT:-newsrc}"
REMOTE_PLAYABLES="${REMOTE_PLAYABLES_ROOT:-/opt/xiaoxiao/gamecenter/playables}"
REMOTE_MCHAT="${REMOTE_MCHAT:-/opt/xiaoxiao/mchat}"
LOCAL_GC="${LOCAL_GAMECENTER:-$HOME/dev/gamecenter-server}"

if [[ -z "$SLUG" ]]; then
  echo "usage: $0 [ssh_host] <slug> [local_project_dir]" >&2
  exit 1
fi

if [[ -z "$PROJECT_DIR" ]]; then
  OUTER="$LOCAL_GC/$REMOTE_PARENT/$SLUG"
  PROJECT_DIR="$(gc_resolve_nested_project_dir "$OUTER")"
fi

BUILD_OUT="$PROJECT_DIR/build/web-mobile"
if [[ ! -d "$BUILD_OUT" || -z "$(ls -A "$BUILD_OUT" 2>/dev/null || true)" ]]; then
  echo "Missing build/web-mobile — run gamecenter-local-build-project.sh first" >&2
  exit 1
fi

echo "Resolving remote Cocos project dir for slug=$SLUG ..."
REMOTE_PROJECT_DIR="$(
  ssh "$RSYNC_HOST" "python3 '$REMOTE_MCHAT/ops/scripts/resolve-gamecenter-project.py' '$REMOTE_MCHAT' '$SLUG' 2>/dev/null || true"
)"
if [[ -z "$REMOTE_PROJECT_DIR" ]]; then
  REMOTE_PROJECT_DIR="${REMOTE_ROOT}/${REMOTE_PARENT}/${SLUG}"
  echo "Warning: using fallback remote project path: $REMOTE_PROJECT_DIR" >&2
else
  echo "Remote project dir: $REMOTE_PROJECT_DIR"
fi

REMOTE_BUILD="${REMOTE_PROJECT_DIR}/build/web-mobile"

echo ""
echo "[1/3] Push sources -> ${RSYNC_HOST}:${REMOTE_PROJECT_DIR}/"
rsync -avz \
  --include 'assets/***' \
  --include 'settings/***' \
  --include 'packages/***' \
  --include 'src/***' \
  --include 'extensions/***' \
  --include 'project.json' \
  --include 'package.json' \
  --include 'tsconfig.json' \
  --exclude '*' \
  "$PROJECT_DIR/" "${RSYNC_HOST}:${REMOTE_PROJECT_DIR}/"

echo ""
echo "[2/3] Push build (5099 reads this) -> ${RSYNC_HOST}:${REMOTE_BUILD}/"
ssh "$RSYNC_HOST" "mkdir -p '${REMOTE_BUILD}'"
rsync -avz --delete "$BUILD_OUT/" "${RSYNC_HOST}:${REMOTE_BUILD}/"

echo ""
echo "[3/3] Mirror to playables/releases (DevBridge / xyx nginx)"
RELEASE_ID="local-$(date +%Y%m%d-%H%M%S)"
REMOTE_RELEASE="${REMOTE_PLAYABLES}/${SLUG}/releases/${RELEASE_ID}"
ssh "$RSYNC_HOST" "mkdir -p '${REMOTE_PLAYABLES}/${SLUG}/releases'"
rsync -avz --delete "$BUILD_OUT/" "${RSYNC_HOST}:${REMOTE_RELEASE}/"
ssh "$RSYNC_HOST" "cd '${REMOTE_PLAYABLES}/${SLUG}' && ln -sfn 'releases/${RELEASE_ID}' current 2>/dev/null || true"

INDEX_MTIME="$(
  ssh "$RSYNC_HOST" "stat -f '%Sm' -t '%Y-%m-%d %H:%M:%S' '${REMOTE_BUILD}/index.html' 2>/dev/null || stat -c '%y' '${REMOTE_BUILD}/index.html' 2>/dev/null | cut -d. -f1 || true"
)"

echo ""
echo "Upload OK"
echo "  live build (5099): ${REMOTE_BUILD}"
echo "  playables:         ${REMOTE_PLAYABLES}/${SLUG}/current -> releases/${RELEASE_ID}"
if [[ -n "$INDEX_MTIME" ]]; then
  echo "  index.html mtime:  $INDEX_MTIME"
fi
echo ""
echo "Hard refresh (Cmd+Shift+R):"
echo "  http://${HOST_IP}:5099/${SLUG}/"
echo "  https://xyx.9235.net/${SLUG}/"
