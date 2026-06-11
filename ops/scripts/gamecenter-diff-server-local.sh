#!/usr/bin/env bash
# Compare server vs local GameCenter source for a slug (debug pull/sync issues).
# Usage: gamecenter-diff-server-local.sh [ssh_host] <slug> [relative_file]
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
REL_FILE="${3:-assets/scripts/ui/UILoading.ts}"
SSH_USER="${SSH_USER:-xiaoxiao}"
REMOTE_MCHAT="${REMOTE_MCHAT:-/opt/xiaoxiao/mchat}"
REMOTE_PARENT="${REMOTE_PROJECT_PARENT:-newsrc}"
LOCAL_GC="${LOCAL_GAMECENTER:-$HOME/dev/gamecenter-server}"

if [[ "$HOST_RAW" == *@* ]]; then
  RSYNC_HOST="$HOST_RAW"
else
  RSYNC_HOST="${SSH_USER}@${HOST_RAW}"
fi

if [[ -z "$SLUG" ]]; then
  echo "usage: $0 [ssh_host] <slug> [relative_file]" >&2
  echo "example: $0 10.98.8.15 pkg0002-3-x-3-8-3ts assets/scripts/ui/UIMain.ts" >&2
  exit 1
fi

REMOTE_PROJECT="$(gc_remote_project_dir "$HOST_RAW" "$SLUG" "$REMOTE_MCHAT" || true)"
if [[ -n "$REMOTE_PROJECT" ]]; then
  REMOTE_OUTER="$(gc_slug_outer_from_project_dir "$REMOTE_PROJECT" "$SLUG" "${REMOTE_GAMECENTER_ROOT:-/opt/xiaoxiao/gamecenter}" || true)"
  if [[ -n "$REMOTE_OUTER" ]]; then
    REMOTE_PARENT="$(basename "$(dirname "$REMOTE_OUTER")")"
  fi
fi
LOCAL_OUTER="$LOCAL_GC/$REMOTE_PARENT/$SLUG"
LOCAL_PROJECT="$(gc_resolve_nested_project_dir "$LOCAL_OUTER")"

echo "slug:           $SLUG"
echo "remote project: ${REMOTE_PROJECT:-<unresolved>}"
echo "local project:  $LOCAL_PROJECT"
echo "compare file:   $REL_FILE"
echo ""

if [[ -z "$REMOTE_PROJECT" ]]; then
  echo "Cannot resolve remote project — check DevBridge source_root / extra_source_roots on server." >&2
  exit 1
fi

REMOTE_FILE="$REMOTE_PROJECT/$REL_FILE"
LOCAL_FILE="$LOCAL_PROJECT/$REL_FILE"

echo "==> Server source snippet"
ssh "$RSYNC_HOST" "grep -n 'ver:' '$REMOTE_FILE' 2>/dev/null | head -5 || echo '(file missing)'"
echo ""
echo "==> Local source snippet"
grep -n 'ver:' "$LOCAL_FILE" 2>/dev/null | head -5 || echo "(file missing)"
echo ""

CMP="$(gc_compare_file_md5 "$LOCAL_FILE" "$RSYNC_HOST" "$REMOTE_FILE" || true)"
if [[ "$CMP" == match* ]]; then
  echo "md5: MATCH (${CMP#match	})"
  exit 0
fi
echo "md5: DIFF"
echo "  $CMP"
echo ""
echo "Fix: run pull only —"
echo "  $SCRIPT_DIR/gamecenter-sync-from-server.sh $HOST_RAW"
echo "  or full pipeline without --skip-pull"
exit 1
