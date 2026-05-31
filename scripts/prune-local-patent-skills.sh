#!/usr/bin/env bash
# Remove patent-* skill copies from mchat/skills/ (use EXTRA_SKILLS_DIRS instead).
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
SKILLS="$ROOT/skills"

removed=0
for name in patent-search patent-report patent-transaction patent-disclosure; do
  dir="$SKILLS/$name"
  if [[ -d "$dir" ]]; then
    echo "→ Removing $dir"
    rm -rf "$dir"
    removed=$((removed + 1))
  fi
done

if [[ "$removed" -eq 0 ]]; then
  echo "No local patent-* directories under skills/ (already clean)."
else
  echo "✅ Removed $removed patent skill dir(s). Configure EXTRA_SKILLS_DIRS to your patents repo."
fi
