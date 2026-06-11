#!/usr/bin/env bash
# Unmount SSHFS GameCenter mount.
# Usage: gamecenter-umount.sh [local_mount_point]
set -euo pipefail

MOUNT="${1:-$HOME/mnt/gamecenter-server}"

if ! mount | grep -q " on ${MOUNT} "; then
  echo "Not mounted: $MOUNT"
  exit 0
fi

diskutil unmount "$MOUNT" 2>/dev/null || umount "$MOUNT"
echo "Unmounted $MOUNT"
