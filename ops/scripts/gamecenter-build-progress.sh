#!/usr/bin/env bash
# Quick GameCenter build progress from mchat DevBridge build records.
#
# Usage:
#   gamecenter-build-progress.sh mmwfk
#   gamecenter-build-progress.sh 10.98.8.15 mmwfk
#   gamecenter-build-progress.sh mmwfk --watch
#   gamecenter-build-progress.sh mmwfk --watch 5   # poll every 5s
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
# shellcheck disable=SC1091
source "$SCRIPT_DIR/gamecenter-lib.sh"

WATCH=0
INTERVAL=3
POSITIONAL=()

while [[ $# -gt 0 ]]; do
  case "$1" in
    --watch)
      WATCH=1
      shift
      ;;
    --help|-h)
      sed -n '2,8p' "$0"
      exit 0
      ;;
    *)
      POSITIONAL+=("$1")
      shift
      ;;
  esac
done

set -- "${POSITIONAL[@]}"

HOST_RAW="${1:-10.98.8.15}"
SLUG="${2:-}"
if [[ -z "$SLUG" ]]; then
  SLUG="$HOST_RAW"
  HOST_RAW="10.98.8.15"
fi
if [[ "${3:-}" =~ ^[0-9]+$ ]]; then
  INTERVAL="$3"
fi

if [[ -z "$SLUG" ]]; then
  echo "usage: $0 [ssh_host] <slug> [--watch] [interval_seconds]" >&2
  exit 1
fi

if [[ "$HOST_RAW" == *@* ]]; then
  SSH_TARGET="$HOST_RAW"
  HOST_IP="${HOST_RAW#*@}"
else
  SSH_USER="${SSH_USER:-xiaoxiao}"
  SSH_TARGET="${SSH_USER}@${HOST_RAW}"
  HOST_IP="$HOST_RAW"
fi

REMOTE_MCHAT="${REMOTE_MCHAT:-/opt/xiaoxiao/mchat}"
DATA_ROOT="${GAMECENTER_BRIDGE_DATA_ROOT:-$REMOTE_MCHAT/data/devbridge/gamecenter}"

print_progress() {
  ssh "$SSH_TARGET" "python3 -" "$DATA_ROOT" "$SLUG" <<'PY'
import json
import sys
from pathlib import Path

data_root = Path(sys.argv[1])
slug = sys.argv[2]
builds_root = data_root / slug / "builds"
if not builds_root.is_dir():
    print(f"NO_BUILDS\t{slug}\t(no build records under {builds_root})")
    raise SystemExit(0)

entries = []
for entry in sorted(builds_root.iterdir(), key=lambda p: p.name, reverse=True):
    meta_path = entry / "metadata.json"
    if not meta_path.is_file():
        continue
    try:
        meta = json.loads(meta_path.read_text(encoding="utf-8"))
    except Exception:
        continue
    meta["_dir"] = str(entry)
    entries.append(meta)

if not entries:
    print(f"NO_BUILDS\t{slug}\t(empty builds dir)")
    raise SystemExit(0)

latest = entries[0]
status = str(latest.get("status") or "unknown")
build_id = str(latest.get("id") or "")
created = str(latest.get("created_at") or "")
summary = str(latest.get("summary") or "")
rc = latest.get("returncode")
active = status in {"queued", "running"}

print(f"STATUS\t{slug}\t{status}\t{build_id[:8]}\t{created}\tactive={active}")
if summary:
    print(f"SUMMARY\t{summary}")
if rc is not None:
    print(f"EXIT\t{rc}")

build_dir = Path(latest["_dir"])
for name in ("stdout.log", "stderr.log"):
    path = build_dir / name
    if not path.is_file():
        continue
    text = path.read_text(encoding="utf-8", errors="replace").strip()
    if not text:
        continue
    tail = text[-1800:]
    print(f"--- {name} (tail) ---")
    print(tail)
    print(f"--- end {name} ---")

try:
    import subprocess
    out = subprocess.run(
        ["redis-cli", "LLEN", "mchat:build:queue"],
        capture_output=True,
        text=True,
        timeout=2,
    )
    if out.returncode == 0 and out.stdout.strip().isdigit():
        print(f"QUEUE\tmchat:build:queue={out.stdout.strip()}")
except Exception:
    pass

print(f"ACTIVE\t{1 if active else 0}")
PY
}

while true; do
  echo "==> $(date '+%H:%M:%S') build progress · $SLUG @ $SSH_TARGET"
  OUTPUT="$(print_progress || true)"
  echo "$OUTPUT"
  if [[ "$WATCH" -eq 0 ]]; then
    break
  fi
  if echo "$OUTPUT" | grep -q '^ACTIVE	0'; then
    echo "==> done (not queued/running)"
    break
  fi
  sleep "$INTERVAL"
done

PLAY_PATH="$(gc_play_path "$SLUG" 2>/dev/null || printf '/%s/' "$SLUG")"
echo ""
echo "==> Play URL probe: http://${HOST_IP}:5099${PLAY_PATH}"
curl -sI "http://${HOST_IP}:5099${PLAY_PATH}" | head -3 || true
