#!/usr/bin/env bash
# Rsync GameCenter sources from server to local (no SSHFS / brew required).
# Usage: gamecenter-sync-from-server.sh [ssh_host] [local_dir]
set -euo pipefail

HOST_RAW="${1:-10.98.8.15}"
LOCAL="${2:-$HOME/dev/gamecenter-server}"
SSH_USER="${SSH_USER:-xiaoxiao}"
if [[ "$HOST_RAW" == *@* ]]; then
  RSYNC_HOST="$HOST_RAW"
else
  RSYNC_HOST="${SSH_USER}@${HOST_RAW}"
fi
REMOTE_ROOT="${REMOTE_GAMECENTER_ROOT:-/opt/xiaoxiao/gamecenter}"

mkdir -p "$LOCAL"

echo "Pulling ${RSYNC_HOST}:${REMOTE_ROOT}/ -> $LOCAL"
rsync -avz --progress \
  --exclude 'node_modules/' \
  --exclude 'library/' \
  --exclude 'temp/' \
  --exclude 'build/' \
  --exclude '.git/' \
  "${RSYNC_HOST}:${REMOTE_ROOT}/" "$LOCAL/"

echo "Done. Local tree: $LOCAL"
echo "Edit/build locally, then: ops/scripts/gamecenter-sync-build-to-server.sh $HOST_RAW <slug>"
