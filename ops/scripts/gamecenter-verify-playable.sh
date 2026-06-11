#!/usr/bin/env bash
# Verify server playable: GameCenter :5099 uses project/build/web-mobile.
# Usage: gamecenter-verify-playable.sh [ssh_host] <slug>
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
HOST_RAW="${1:-10.98.8.15}"
SLUG="${2:-}"
SSH_USER="${SSH_USER:-xiaoxiao}"
REMOTE_MCHAT="${REMOTE_MCHAT:-/opt/xiaoxiao/mchat}"
REMOTE_PLAYABLES="${REMOTE_PLAYABLES_ROOT:-/opt/xiaoxiao/gamecenter/playables}"

if [[ "$HOST_RAW" == *@* ]]; then
  SSH_TARGET="$HOST_RAW"
  HOST_IP="${HOST_RAW#*@}"
else
  SSH_TARGET="${SSH_USER}@${HOST_RAW}"
  HOST_IP="$HOST_RAW"
fi

if [[ -z "$SLUG" ]]; then
  echo "usage: $0 [ssh_host] <slug>" >&2
  exit 1
fi

REMOTE_PROJECT="$(
  ssh "$SSH_TARGET" "python3 '$REMOTE_MCHAT/ops/scripts/resolve-gamecenter-project.py' '$REMOTE_MCHAT' '$SLUG' 2>/dev/null || true"
)"
REMOTE_BUILD="${REMOTE_PROJECT}/build/web-mobile"

echo "==> Live build (what :5099 serves)"
echo "    ${SSH_TARGET}:${REMOTE_BUILD}"
ssh "$SSH_TARGET" "ls -la '${REMOTE_BUILD}/index.html' 2>/dev/null || echo 'MISSING: build/web-mobile'"

echo ""
echo "==> Playables (DevBridge publish mirror)"
echo "    ${SSH_TARGET}:${REMOTE_PLAYABLES}/${SLUG}/"
ssh "$SSH_TARGET" "ls -la '${REMOTE_PLAYABLES}/${SLUG}/current' 2>/dev/null || echo '(no playables entry yet — OK if using build/web-mobile only)'"

echo ""
echo "==> Source ver:1.0 in UILoading.ts"
ssh "$SSH_TARGET" "grep -n \"ver:1.0\" '${REMOTE_PROJECT}/assets/scripts/ui/UILoading.ts' 2>/dev/null | head -2 || echo 'not found in source'"

echo ""
echo "==> HTTP probe"
curl -sI "http://${HOST_IP}:5099/${SLUG}/" | head -5 || true
