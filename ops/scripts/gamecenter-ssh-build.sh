#!/usr/bin/env bash
# Trigger a web-mobile build on the REMOTE server over SSH.
#
# Important:
# - Compiles the project files ON THE SERVER (e.g. Agent / DevBridge edits there).
# - Does NOT use your local Mac checkout of mchat or gamecenter source.
# - Without Cocos on the server, it may only REUSE an old build/web-mobile folder.
#
# Usage: gamecenter-ssh-build.sh [ssh_host] <project_slug> [--force]
set -euo pipefail

HOST="${1:-10.98.8.15}"
SLUG=""
FORCE_ARG=""

shift $(( $# > 0 ? 1 : 0 )) || true
while [[ $# -gt 0 ]]; do
  case "$1" in
    --force)
      FORCE_ARG="--force"
      shift
      ;;
    *)
      if [[ -z "$SLUG" ]]; then
        SLUG="$1"
      else
        echo "unexpected argument: $1" >&2
        exit 1
      fi
      shift
      ;;
  esac
done

if [[ -z "$SLUG" ]]; then
  echo "usage: $0 [ssh_host] <project_slug> [--force]" >&2
  echo "example: $0 10.98.8.15 pkg0002-3-x-3-8-3ts" >&2
  echo "         $0 10.98.8.15 pkg0002-3-x-3-8-3ts --force  # fail if Cocos not configured" >&2
  exit 1
fi

REMOTE_MCHAT="${REMOTE_MCHAT:-/opt/xiaoxiao/mchat}"
echo "Remote build on $HOST — slug=$SLUG (server project tree + server Cocos, not local code)"
ssh "$HOST" "bash '$REMOTE_MCHAT/ops/scripts/gamecenter-remote-build.sh' '$SLUG' $FORCE_ARG"
