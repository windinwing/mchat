#!/usr/bin/env bash
# 从 patents 源仓库同步到 mchat/skills
set -euo pipefail
SRC="${1:-/Users/xiaoxiao/dev/skills/patents}"
DST="${2:-/Users/xiaoxiao/dev/mchat/skills}"
RSYNC_EXCLUDE=(--exclude 'config.json' --exclude 'dist/' --exclude '__pycache__/' --exclude '.git/')

rsync -a "${RSYNC_EXCLUDE[@]}" "$SRC/patent-search/" "$DST/patent-search/"
rsync -a "${RSYNC_EXCLUDE[@]}" "$SRC/patent-transaction/" "$DST/patent-transaction/"
rsync -a "${RSYNC_EXCLUDE[@]}" "$SRC/patent-disclosure/" "$DST/patent-disclosure/"
rsync -a "${RSYNC_EXCLUDE[@]}" "$SRC/patent-report/" "$DST/patent-report/"
if [ -x "$SRC/patent-report/scripts/ensure-font.sh" ]; then
  bash "$SRC/patent-report/scripts/ensure-font.sh" >/dev/null 2>&1 || true
  if [ -f "$SRC/patent-report/fonts/NotoSansCJKsc-Regular.otf" ]; then
    mkdir -p "$DST/patent-report/fonts"
    cp -f "$SRC/patent-report/fonts/NotoSansCJKsc-Regular.otf" "$DST/patent-report/fonts/"
  fi
fi

echo "✅ 已同步到 $DST"
echo "   patent-search patent-transaction patent-disclosure patent-report"
echo "   重启 mchat 后端或执行: cd src/backend && <venv-python> ../../scripts/reload-patent-skills.py"
