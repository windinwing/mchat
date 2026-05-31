#!/usr/bin/env bash
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/../.." && pwd)"
cd "$ROOT"

chmod +x .githooks/pre-push
git config core.hooksPath .githooks

echo "Git hooks installed (core.hooksPath=.githooks)"
echo "  origin (GitHub): 仅允许本地 dev 推送到 dev/main"
echo "  发布 main: git push origin dev:main"
echo "  private: 无限制"
