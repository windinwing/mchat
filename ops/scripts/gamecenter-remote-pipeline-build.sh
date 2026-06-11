#!/usr/bin/env bash
# Run ON the MChat server as DevBridge build_command (SSH to Mac/Windows build machine).
# Usage: gamecenter-remote-pipeline-build.sh <slug> [build_id]
#
# Server .env or environment:
#   GAMECENTER_BUILD_SSH_HOST=192.168.x.x    # Mac mini / Windows build machine
#   GAMECENTER_BUILD_SSH_USER=build          # optional, default build
#   GAMECENTER_BUILD_PIPELINE_SCRIPT=/opt/mchat/ops/scripts/gamecenter-local-pipeline.sh
#   GAMECENTER_BUILD_SSH_IDENTITY=~/.ssh/id_gamecenter_build
#   GAMECENTER_DEPLOY_HOST=10.98.8.15        # rsync target (this server or its IP)
#
# DevBridge build_command example:
#   bash /opt/xiaoxiao/mchat/ops/scripts/gamecenter-remote-pipeline-build.sh {slug} {build_id}
set -euo pipefail

# DevBridge subprocess may not inherit .env; load server env when present.
MCHAT_ENV_FILE="${MCHAT_ENV_FILE:-/opt/xiaoxiao/mchat/.env}"
if [[ -f "$MCHAT_ENV_FILE" ]]; then
  while IFS= read -r line; do
    case "$line" in
      ''|\#*) continue ;;
      GAMECENTER_BUILD_*|GAMECENTER_DEPLOY_*|GAMECENTER_AUTO_BUILD_*)
        export "$line"
        ;;
    esac
  done < "$MCHAT_ENV_FILE"
fi

SLUG="${1:-}"
BUILD_ID="${2:-${GAMECENTER_BUILD_ID:-}}"
if [[ -z "$SLUG" ]]; then
  echo "usage: $0 <slug> [build_id]" >&2
  exit 1
fi
export GAMECENTER_BUILD_ID="$BUILD_ID"

SSH_HOST="${GAMECENTER_BUILD_SSH_HOST:-}"
SSH_USER="${GAMECENTER_BUILD_SSH_USER:-build}"
PIPELINE="${GAMECENTER_BUILD_PIPELINE_SCRIPT:-/opt/mchat/ops/scripts/gamecenter-local-pipeline.sh}"
SSH_IDENTITY="${GAMECENTER_BUILD_SSH_IDENTITY:-$HOME/.ssh/id_gamecenter_build}"
DEPLOY_HOST="${GAMECENTER_DEPLOY_HOST:-10.98.8.15}"

if [[ -z "$SSH_HOST" ]]; then
  echo "GAMECENTER_BUILD_SSH_HOST is not set (Mac/Windows build machine IP/hostname)" >&2
  exit 1
fi

REMOTE_MCHAT="${REMOTE_MCHAT:-/opt/xiaoxiao/mchat}"
PROJECT_DIR="$(
  python3 "${REMOTE_MCHAT}/ops/scripts/resolve-gamecenter-project.py" "${REMOTE_MCHAT}" "${SLUG}" 2>/dev/null || true
)"
COCOS_VER=""
COCOS_MAJOR=""
if [[ -n "$PROJECT_DIR" && -f "${PROJECT_DIR}/project.json" ]]; then
  COCOS_VER="$(grep '"version"' "${PROJECT_DIR}/project.json" 2>/dev/null | head -1 | sed -E 's/.*"version"[[:space:]]*:[[:space:]]*"([^"]+)".*/\1/')"
  COCOS_MAJOR="${COCOS_VER%%.*}"
fi

# Cocos 2.x over Windows SSH often fail (Session 0). Prefer HTTP agent when configured.
# Also avoid --force for 2.x unless GAMECENTER_BUILD_FORCE=1.
FORCE_FLAG=""
if [[ "${GAMECENTER_BUILD_FORCE:-}" == "1" ]]; then
  FORCE_FLAG="--force"
elif [[ "$COCOS_MAJOR" == "2" ]]; then
  echo "Cocos 2.x (${COCOS_VER}): incremental build (no --force). Set GAMECENTER_BUILD_FORCE=1 to override."
else
  FORCE_FLAG="--force"
fi

AGENT_URL="${GAMECENTER_BUILD_AGENT_URL:-}"
AGENT_TOKEN="${GAMECENTER_BUILD_AGENT_TOKEN:-}"
USE_AGENT=0
if [[ -n "$AGENT_URL" && -n "$PROJECT_DIR" && -f "${PROJECT_DIR}/project.json" ]]; then
  COCOS_MAJOR="${COCOS_VER%%.*}"
  if [[ "$COCOS_MAJOR" == "2" ]]; then
    USE_AGENT=1
  fi
fi

if [[ "$USE_AGENT" -eq 1 ]]; then
  echo "Remote pipeline build: slug=${SLUG} via HTTP agent ${AGENT_URL} force=${FORCE_FLAG:-no}"
  SKIP_PULL_BOOL=""
  if [[ "${GAMECENTER_BUILD_SKIP_PULL:-}" == "1" ]]; then
    SKIP_PULL_BOOL=1
  fi
  PAYLOAD="$(
    SLUG="$SLUG" DEPLOY_HOST="$DEPLOY_HOST" FORCE_BOOL="${FORCE_FLAG:+1}" SKIP_PULL_BOOL="$SKIP_PULL_BOOL" BUILD_ID="${BUILD_ID:-}" \
      python3 -c 'import json,os; print(json.dumps({"slug":os.environ["SLUG"],"deploy_host":os.environ["DEPLOY_HOST"],"force":os.environ.get("FORCE_BOOL")=="1","skip_pull":os.environ.get("SKIP_PULL_BOOL")=="1","build_id":os.environ.get("BUILD_ID") or None}))'
  )"
  CURL_ARGS=(-sS -m "${GAMECENTER_BUILD_TIMEOUT_SECONDS:-1800}" -X POST "${AGENT_URL%/}/v1/build" -H "Content-Type: application/json")
  if [[ -n "$AGENT_TOKEN" ]]; then
    CURL_ARGS+=(-H "Authorization: Bearer ${AGENT_TOKEN}")
  fi
  CURL_ARGS+=(-d "$PAYLOAD")
  RESP="$(curl "${CURL_ARGS[@]}" 2>&1 || true)"
  if [[ -z "$RESP" || "$RESP" == curl:* ]]; then
    echo "HTTP agent request failed: ${RESP:-no response}. Is the Windows logon agent running?" >&2
    exit 1
  fi
  echo "$RESP" | python3 -c '
import json,sys
data=json.load(sys.stdin)
print(data.get("stdout") or "", end="")
err=data.get("stderr") or ""
if err.strip():
    print(err, file=sys.stderr, end="")
sys.exit(0 if data.get("ok") else int(data.get("returncode") or 1))
'
  exit $?
fi

echo "Remote pipeline build: slug=${SLUG} host=${SSH_USER}@${SSH_HOST} force=${FORCE_FLAG:-no}"
SSH_ARGS=(-o BatchMode=yes -o ConnectTimeout=20 -o StrictHostKeyChecking=accept-new)
if [[ -n "${SSH_IDENTITY}" && -f "${SSH_IDENTITY}" ]]; then
  SSH_ARGS+=(-i "${SSH_IDENTITY}")
fi
# Windows OpenSSH DefaultShell is often Git Bash; avoid nested `bash` (shell level explosion).
if [[ "$PIPELINE" == /[cC]/* ]]; then
  REMOTE_SHELL='"/c/Program Files/Git/bin/bash.exe"'
  REMOTE_CMD="${REMOTE_SHELL} --noprofile --norc -lc \"'${PIPELINE}' '${DEPLOY_HOST}' '${SLUG}'${FORCE_FLAG:+ ${FORCE_FLAG}}\""
else
  REMOTE_CMD="bash '${PIPELINE}' '${DEPLOY_HOST}' '${SLUG}'${FORCE_FLAG:+ ${FORCE_FLAG}}"
fi
ssh "${SSH_ARGS[@]}" "${SSH_USER}@${SSH_HOST}" "${REMOTE_CMD}"
