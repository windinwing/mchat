#!/usr/bin/env bash
# 从 StockIntelligence 源仓库同步到 mchat/skills
# 每个 skill 内嵌一份 si_common（保证独立可加载，与 dist 打包逻辑一致）
set -euo pipefail
SRC="${1:-/Users/xiaoxiao/dev/skills/StockIntelligence}"
DST="${2:-/Users/xiaoxiao/dev/mchat/skills}"
RSYNC_EXCLUDE=(--exclude 'config.json' --exclude 'dist/' --exclude '__pycache__/' --exclude '.git/' --exclude 'uploads/' --exclude '*.otf')

SKILLS=(quote capital fundamentals research news announcement sentiment analysis)

for s in "${SKILLS[@]}"; do
  name="stock-$s"
  # 同步 skill 本体
  rsync -a "${RSYNC_EXCLUDE[@]}" "$SRC/$name/" "$DST/$name/"
  # 内嵌 si_common（每个 skill 独立可加载）
  mkdir -p "$DST/$name/si_common/providers"
  rsync -a --delete "$SRC/si_common/" "$DST/$name/si_common/" \
    --exclude '__pycache__/'
done

# stock-analysis 需要字体（图表用）
if [ -f "$SRC/stock-analysis/fonts/NotoSansCJKsc-Regular.otf" ]; then
  mkdir -p "$DST/stock-analysis/fonts"
  cp -f "$SRC/stock-analysis/fonts/NotoSansCJKsc-Regular.otf" "$DST/stock-analysis/fonts/"
else
  echo "⚠️  字体未下载，图表中文可能乱码。运行：bash $SRC/stock-analysis/ensure-font.sh"
fi

echo "✅ 已同步到 $DST"
echo "   ${SKILLS[@]/#/stock-}"
echo "   每个 skill 内含 si_common/，独立可加载"
echo "   重启 mchat 后端或执行技能重载"
