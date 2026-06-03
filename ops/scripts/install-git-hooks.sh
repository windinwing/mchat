#!/usr/bin/env bash
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/../.." && pwd)"
cd "$ROOT"

chmod +x .githooks/pre-push
git config core.hooksPath .githooks

echo "Git hooks installed (core.hooksPath=.githooks)"
echo "  origin (GitHub): local dev branch may push to dev/main only"
echo "  release main: git push origin dev:main"
echo "  private remote: unrestricted"
