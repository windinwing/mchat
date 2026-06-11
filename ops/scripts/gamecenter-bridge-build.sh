#!/usr/bin/env bash
# Fixed GameCenter bridge build entry (do not let the agent invent shell).
# Usage: gamecenter-bridge-build.sh <project_dir> [--force]
set -euo pipefail

PROJECT_DIR="${1:-}"
FORCE_REBUILD="${GAMECENTER_FORCE_REBUILD:-0}"
if [[ "${2:-}" == "--force" ]]; then
  FORCE_REBUILD=1
fi

if [[ -z "$PROJECT_DIR" || ! -d "$PROJECT_DIR" ]]; then
  echo "project dir missing: $PROJECT_DIR" >&2
  exit 1
fi

BUILD_OUT="$PROJECT_DIR/build/web-mobile"
COCOS_BIN="${GAMECENTER_COCOS_CREATOR_BIN:-}"

BUILD_DEBUG="${GAMECENTER_BUILD_DEBUG:-false}"

if [[ -n "$COCOS_BIN" && -x "$COCOS_BIN" ]]; then
  echo "Building with Cocos Creator: $COCOS_BIN (debug=${BUILD_DEBUG})"
  if command -v xvfb-run >/dev/null 2>&1; then
    xvfb-run -a "$COCOS_BIN" --project "$PROJECT_DIR" --build "platform=web-mobile;debug=${BUILD_DEBUG}" 2>/dev/null \
      || "$COCOS_BIN" --project "$PROJECT_DIR" --build "platform=web-mobile;debug=${BUILD_DEBUG}"
  else
    "$COCOS_BIN" --project "$PROJECT_DIR" --build "platform=web-mobile;debug=${BUILD_DEBUG}"
  fi
  echo "Build finished: $BUILD_OUT"
  exit 0
fi

if [[ "$FORCE_REBUILD" == "1" ]]; then
  echo "FORCE rebuild requested but GAMECENTER_COCOS_CREATOR_BIN is missing or not executable: ${COCOS_BIN:-<empty>}" >&2
  echo "Set it in DevBridge admin settings (cocos_creator_bin) or server .env, then retry." >&2
  exit 1
fi

if [[ -d "$BUILD_OUT" && -n "$(ls -A "$BUILD_OUT" 2>/dev/null || true)" ]]; then
  echo "Reuse existing web-mobile build at $BUILD_OUT"
  echo "  (Agent edits are NOT compiled until Cocos runs. Set cocos_creator_bin or pass --force to fail instead of reuse.)"
  exit 0
fi

echo "No web-mobile build found and GAMECENTER_COCOS_CREATOR_BIN is not set." >&2
exit 1
