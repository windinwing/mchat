#!/usr/bin/env bash
# List DevBridge patch history on server (proof that Agent really wrote files).
# Usage: gamecenter-list-changes.sh [ssh_host] <slug> [path_filter]
set -euo pipefail

HOST_RAW="${1:-10.98.8.15}"
SLUG="${2:-}"
FILTER="${3:-}"
SSH_USER="${SSH_USER:-xiaoxiao}"
REMOTE_MCHAT="${REMOTE_MCHAT:-/opt/xiaoxiao/mchat}"

if [[ "$HOST_RAW" == *@* ]]; then
  SSH_TARGET="$HOST_RAW"
else
  SSH_TARGET="${SSH_USER}@${HOST_RAW}"
fi

if [[ -z "$SLUG" ]]; then
  echo "usage: $0 [ssh_host] <slug> [path_filter]" >&2
  echo "example: $0 10.98.8.15 pkg0002-3-x-3-8-3ts Main.ts" >&2
  exit 1
fi

CHANGES_ROOT="${REMOTE_MCHAT}/data/devbridge/gamecenter/${SLUG}/changes"

echo "DevBridge changes on ${SSH_TARGET}:${CHANGES_ROOT}"
echo ""

ssh "$SSH_TARGET" "python3 - <<'PY'
import json
import sys
from pathlib import Path

slug = ${SLUG@Q}
changes_root = Path(${CHANGES_ROOT@Q})
path_filter = ${FILTER@Q}.strip().lower()

rows = []
if changes_root.is_dir():
    for entry in sorted(changes_root.iterdir(), key=lambda p: p.name, reverse=True):
        meta = entry / 'metadata.json'
        if not meta.is_file():
            continue
        try:
            data = json.loads(meta.read_text(encoding='utf-8'))
        except Exception:
            continue
        path = str(data.get('path') or '')
        if path_filter and path_filter not in path.lower():
            continue
        rows.append(data)

if not rows:
    print('(no matching changes — Agent patch likely never ran or path filter too strict)')
    sys.exit(0)

for data in rows:
    print(f\"{data.get('created_at')}  {data.get('path')}\")
    print(f\"  id={data.get('id')}  status={data.get('status')}  summary={data.get('summary') or '-'}\")
    print(f\"  after_sha256={str(data.get('after_sha256') or '')[:16]}…\")
    print()
PY"

PROJ="$(ssh "$SSH_TARGET" "python3 '${REMOTE_MCHAT}/ops/scripts/resolve-gamecenter-project.py' '${REMOTE_MCHAT}' '${SLUG}' 2>/dev/null || true")"
if [[ -n "$PROJ" && -n "$FILTER" ]]; then
  echo "Server file grep (${FILTER}):"
  ssh "$SSH_TARGET" "find '$PROJ' -path '*${FILTER}*' -type f 2>/dev/null | while read -r f; do echo \"  \$f\"; ls -la \"\$f\"; done"
fi
