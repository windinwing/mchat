#!/usr/bin/env bash
# Mount remote GameCenter source tree locally via SSHFS (macOS: brew install macfuse sshfs).
# Usage: gamecenter-mount.sh [ssh_host] [local_mount_point]
set -euo pipefail

HOST="${1:-10.98.8.15}"
MOUNT="${2:-$HOME/mnt/gamecenter-server}"
REMOTE_ROOT="${REMOTE_GAMECENTER_ROOT:-/opt/xiaoxiao/gamecenter}"
USER="${SSH_USER:-xiaoxiao}"

mkdir -p "$MOUNT"

if mount | grep -q " on ${MOUNT} "; then
  echo "Already mounted: $MOUNT"
  exit 0
fi

if ! command -v sshfs >/dev/null 2>&1; then
  echo "sshfs not found. On macOS: brew install macfuse sshfs" >&2
  exit 1
fi

echo "Mounting ${USER}@${HOST}:${REMOTE_ROOT} -> $MOUNT"
sshfs "${USER}@${HOST}:${REMOTE_ROOT}" "$MOUNT" -o volname=gamecenter-server,follow_symlinks,reconnect,ServerAliveInterval=15

echo "Mounted. Example project:"
echo "  ls \"$MOUNT/src\""
echo "Local edit + build, then: ops/scripts/gamecenter-push-playable.sh $HOST <slug>"
