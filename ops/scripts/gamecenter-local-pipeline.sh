#!/usr/bin/env bash
# One-shot: pull project from server -> build on this Mac -> push back to server.
# Usage: gamecenter-local-pipeline.sh <host> <project_slug> [--force] [--skip-pull]
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
# shellcheck disable=SC1091
source "$SCRIPT_DIR/gamecenter-lib.sh"
if [[ -f "$SCRIPT_DIR/gamecenter-local.env" ]]; then
  # shellcheck disable=SC1091
  source "$SCRIPT_DIR/gamecenter-local.env"
fi

HOST_RAW="${1:-}"
SLUG="${2:-}"
FORCE_BUILD=0
SKIP_PULL=0
SKIP_PUSH=0

shift $(( $# > 0 ? 1 : 0 )) 2>/dev/null || true
shift $(( $# > 0 ? 1 : 0 )) 2>/dev/null || true
while [[ $# -gt 0 ]]; do
  case "$1" in
    --force) FORCE_BUILD=1; shift ;;
    --skip-pull) SKIP_PULL=1; shift ;;
    --skip-push) SKIP_PUSH=1; shift ;;
    *)
      echo "unknown option: $1" >&2
      exit 1
      ;;
  esac
done

if [[ -z "$HOST_RAW" || -z "$SLUG" ]]; then
  echo "usage: $0 <host> <project_slug> [--force] [--skip-pull] [--skip-push]" >&2
  echo "example: $0 10.98.8.15 pkg0002-3-x-3-8-3ts --force" >&2
  exit 1
fi

SSH_USER="${SSH_USER:-xiaoxiao}"
if [[ "$HOST_RAW" == *@* ]]; then
  RSYNC_HOST="$HOST_RAW"
  HOST_LABEL="$HOST_RAW"
else
  RSYNC_HOST="${SSH_USER}@${HOST_RAW}"
  HOST_LABEL="$HOST_RAW"
fi

LOCAL_GC="${LOCAL_GAMECENTER:-$HOME/dev/gamecenter-server}"
REMOTE_ROOT="${REMOTE_GAMECENTER_ROOT:-/opt/xiaoxiao/gamecenter}"
REMOTE_PARENT="${REMOTE_PROJECT_PARENT:-newsrc}"

LOCAL_OUTER="$LOCAL_GC/$REMOTE_PARENT/$SLUG"
REMOTE_OUTER="${REMOTE_ROOT}/${REMOTE_PARENT}/${SLUG}"

echo "========================================"
echo "GameCenter local pipeline"
echo "  host:    $HOST_LABEL"
echo "  slug:    $SLUG"
echo "  local:   $LOCAL_GC"
echo "========================================"

if [[ "$SKIP_PULL" -eq 0 ]]; then
  echo ""
  echo "==> [1/3] Pull from server"
  REMOTE_PROJECT_DIR="$(gc_remote_project_dir "$HOST_RAW" "$SLUG" "${REMOTE_MCHAT:-/opt/xiaoxiao/mchat}" || true)"
  echo "  remote outer:  ${RSYNC_HOST}:${REMOTE_OUTER}/"
  if [[ -n "$REMOTE_PROJECT_DIR" ]]; then
    echo "  remote nested: ${REMOTE_PROJECT_DIR}"
  else
    echo "  remote nested: (resolve failed — still pulling outer slug dir)"
  fi
  echo "  local outer:   $LOCAL_OUTER/"
  mkdir -p "$LOCAL_OUTER"
  PULL_LOG="$(mktemp)"
  rsync -avz --progress \
    --exclude 'node_modules/' \
    --exclude 'library/' \
    --exclude 'temp/' \
    --exclude 'build/' \
    --exclude '.git/' \
    "${RSYNC_HOST}:${REMOTE_OUTER}/" "$LOCAL_OUTER/" 2>&1 | tee "$PULL_LOG"
  PULL_XFER="$(grep -c '^[^ ].*100%' "$PULL_LOG" 2>/dev/null || echo 0)"
  echo "  pull summary: ${PULL_XFER} file(s) updated (0 = already in sync with server)"
  rm -f "$PULL_LOG"
else
  echo ""
  echo "==> [1/3] Pull skipped (--skip-pull)"
  REMOTE_PROJECT_DIR="$(gc_remote_project_dir "$HOST_RAW" "$SLUG" "${REMOTE_MCHAT:-/opt/xiaoxiao/mchat}" || true)"
fi

if [[ ! -d "$LOCAL_OUTER" ]]; then
  echo "Local project missing after pull: $LOCAL_OUTER" >&2
  exit 1
fi

PROJECT_DIR="$(gc_resolve_nested_project_dir "$LOCAL_OUTER")"
echo "Project dir: $PROJECT_DIR"

if [[ "$SKIP_PULL" -eq 0 && -n "$REMOTE_PROJECT_DIR" ]]; then
  MARKER="assets/scripts/ui/UILoading.ts"
  LOCAL_MARKER="$PROJECT_DIR/$MARKER"
  REMOTE_MARKER="$REMOTE_PROJECT_DIR/$MARKER"
  if [[ -f "$LOCAL_MARKER" ]]; then
    CMP="$(gc_compare_file_md5 "$LOCAL_MARKER" "$RSYNC_HOST" "$REMOTE_MARKER" || true)"
    if [[ "$CMP" == match* ]]; then
      echo "Pull verify: $MARKER md5 OK (${CMP#match	})"
    else
      echo "Pull verify FAILED: $MARKER differs from server — check paths or re-run pull" >&2
      echo "  $CMP" >&2
      exit 1
    fi
  fi
fi

echo ""
echo "==> [2/3] Local Cocos build"
BUILD_ARGS=("$PROJECT_DIR")
if [[ "$FORCE_BUILD" -eq 1 ]]; then
  BUILD_ARGS+=("--force")
fi
BUILD_LOG="$(mktemp)"
trap 'rm -f "$BUILD_LOG"' EXIT
set +o pipefail
bash "$SCRIPT_DIR/gamecenter-local-build-project.sh" "${BUILD_ARGS[@]}" 2>&1 | tee "$BUILD_LOG"
BUILD_EXIT="${PIPESTATUS[0]:-1}"
set -o pipefail
if [[ "$BUILD_EXIT" -ne 0 ]]; then
  echo "Warning: build script exited $BUILD_EXIT; checking for web-mobile output anyway." >&2
fi

# Prefer PROJECT_DIR emitted by build script; fallback to scan tree for web-mobile
if grep -q '^PROJECT_DIR=' "$BUILD_LOG"; then
  PROJECT_DIR="$(grep '^PROJECT_DIR=' "$BUILD_LOG" | tail -1 | cut -d= -f2-)"
fi
BUILD_PAIR="$(gc_find_build_output "$LOCAL_OUTER" || true)"
if [[ -n "$BUILD_PAIR" ]]; then
  PROJECT_DIR="${BUILD_PAIR%%$'\t'*}"
  BUILD_OUT="${BUILD_PAIR#*$'\t'}"
else
  BUILD_OUT="$PROJECT_DIR/build/web-mobile"
fi

echo "Build output: $BUILD_OUT"
if [[ ! -d "$BUILD_OUT" || -z "$(ls -A "$BUILD_OUT" 2>/dev/null || true)" ]]; then
  echo "build/web-mobile missing or empty: $BUILD_OUT" >&2
  exit 1
fi

if [[ "$SKIP_PUSH" -eq 0 ]]; then
  echo ""
  echo "==> [3/3] Push sources + build to server"
  bash "$SCRIPT_DIR/gamecenter-sync-build-to-server.sh" "$HOST_RAW" "$SLUG" "$PROJECT_DIR"
else
  echo ""
  echo "==> [3/3] Push skipped (--skip-push)"
fi

echo ""
echo "========================================"
echo "Done. Verify upload:"
bash "$SCRIPT_DIR/gamecenter-verify-playable.sh" "$HOST_RAW" "$SLUG" || true
echo ""
echo "Open playable (hard refresh Cmd+Shift+R):"
echo "  http://${HOST_LABEL%%@*}:5099/${SLUG}/"
echo "  https://xyx.9235.net/${SLUG}/"
echo "========================================"
