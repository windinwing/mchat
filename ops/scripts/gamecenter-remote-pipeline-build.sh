#!/usr/bin/env bash
# Run ON the MChat server as DevBridge build_command (SSH to Mac/Windows build machine).
# Usage: gamecenter-remote-pipeline-build.sh <slug>
#
# Server .env or environment:
#   GAMECENTER_BUILD_SSH_HOST=192.168.x.x    # Mac mini / Windows build machine
#   GAMECENTER_BUILD_SSH_USER=build          # optional, default build
#   GAMECENTER_BUILD_PIPELINE_SCRIPT=/opt/mchat/ops/scripts/gamecenter-local-pipeline.sh
#   GAMECENTER_DEPLOY_HOST=10.98.8.15        # rsync target (this server or its IP)
#
# DevBridge build_command example:
#   bash /opt/xiaoxiao/mchat/ops/scripts/gamecenter-remote-pipeline-build.sh {slug}
set -euo pipefail

SLUG="${1:-}"
if [[ -z "$SLUG" ]]; then
  echo "usage: $0 <slug>" >&2
  exit 1
fi

SSH_HOST="${GAMECENTER_BUILD_SSH_HOST:-}"
SSH_USER="${GAMECENTER_BUILD_SSH_USER:-build}"
PIPELINE="${GAMECENTER_BUILD_PIPELINE_SCRIPT:-/opt/mchat/ops/scripts/gamecenter-local-pipeline.sh}"
DEPLOY_HOST="${GAMECENTER_DEPLOY_HOST:-10.98.8.15}"

if [[ -z "$SSH_HOST" ]]; then
  echo "GAMECENTER_BUILD_SSH_HOST is not set (Mac/Windows build machine IP/hostname)" >&2
  exit 1
fi

echo "Remote pipeline build: slug=${SLUG} host=${SSH_USER}@${SSH_HOST}"
ssh -o BatchMode=yes -o ConnectTimeout=20 -o StrictHostKeyChecking=accept-new \
  "${SSH_USER}@${SSH_HOST}" \
  "bash '${PIPELINE}' '${DEPLOY_HOST}' '${SLUG}' --force"
