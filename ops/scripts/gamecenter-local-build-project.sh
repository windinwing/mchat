#!/usr/bin/env bash
# Build a Cocos project on THIS Mac (rsync copy or SSHFS mount).
# Usage: gamecenter-local-build-project.sh <project_dir> [--force]
# Prints resolved project dir line: PROJECT_DIR=<path>
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
# shellcheck disable=SC1091
source "$SCRIPT_DIR/gamecenter-lib.sh"
if [[ -f "$SCRIPT_DIR/gamecenter-local.env" ]]; then
  # shellcheck disable=SC1091
  source "$SCRIPT_DIR/gamecenter-local.env"
fi

PROJECT_DIR="${1:-}"
FORCE="${2:-}"
if [[ -z "$PROJECT_DIR" || ! -d "$PROJECT_DIR" ]]; then
  echo "usage: $0 <project_dir> [--force]" >&2
  exit 1
fi

PROJECT_DIR="$(gc_resolve_nested_project_dir "$PROJECT_DIR")"
echo "Using project dir: $PROJECT_DIR"

if [[ "$FORCE" == "--force" ]]; then
  echo "Force rebuild: clearing library/ and temp/ (avoid stale Cocos cache)"
  rm -rf "$PROJECT_DIR/library" "$PROJECT_DIR/temp"
fi

discover_cocos_bin() {
  if [[ -n "${GAMECENTER_COCOS_CREATOR_BIN:-}" && -x "${GAMECENTER_COCOS_CREATOR_BIN}" ]]; then
    echo "${GAMECENTER_COCOS_CREATOR_BIN}"
    return 0
  fi
  if [[ -n "${COCOS_CREATOR_BIN:-}" && -x "${COCOS_CREATOR_BIN}" ]]; then
    echo "${COCOS_CREATOR_BIN}"
    return 0
  fi

  local cocos_root="/Applications/Cocos/Creator"
  if [[ -d "$cocos_root" ]]; then
    local ver_dir bin
    while IFS= read -r ver_dir; do
      [[ -n "$ver_dir" ]] || continue
      bin="$ver_dir/CocosCreator.app/Contents/MacOS/CocosCreator"
      if [[ -x "$bin" ]]; then
        echo "$bin"
        return 0
      fi
    done < <(find "$cocos_root" -maxdepth 1 -mindepth 1 -type d -name '3.*' | sort -Vr)
  fi

  # Windows (Git Bash / MSYS): Cocos Dashboard default install dir
  local win_roots=(
    "/c/Program Files/Cocos/Creator"
    "/c/Program Files (x86)/Cocos/Creator"
  )
  local win_root ver_dir win_bin
  for win_root in "${win_roots[@]}"; do
    [[ -d "$win_root" ]] || continue
    while IFS= read -r ver_dir; do
      [[ -n "$ver_dir" ]] || continue
      win_bin="$ver_dir/CocosCreator.exe"
      if [[ -f "$win_bin" ]]; then
        echo "$win_bin"
        return 0
      fi
    done < <(find "$win_root" -maxdepth 1 -mindepth 1 -type d -name '3.*' 2>/dev/null | sort -Vr)
  done

  local candidate
  for candidate in \
    "/Applications/Cocos/Creator/3.8.8/CocosCreator.app/Contents/MacOS/CocosCreator" \
    "/Applications/Cocos/Creator/3.8.3/CocosCreator.app/Contents/MacOS/CocosCreator" \
    "/c/Program Files/Cocos/Creator/3.8.8/CocosCreator.exe" \
    "/c/Program Files/Cocos/Creator/3.8.3/CocosCreator.exe"; do
    if [[ -x "$candidate" || -f "$candidate" ]]; then
      echo "$candidate"
      return 0
    fi
  done
  return 1
}

COCOS_BIN="$(discover_cocos_bin || true)"
BUILD_OUT="$PROJECT_DIR/build/web-mobile"
# debug=true embeds showFPS in web-mobile (application.js). Use false for playable builds.
BUILD_DEBUG="${GAMECENTER_BUILD_DEBUG:-false}"

if [[ -n "$COCOS_BIN" && ( -x "$COCOS_BIN" || -f "$COCOS_BIN" ) ]]; then
  echo "Building with local Cocos: $COCOS_BIN (debug=${BUILD_DEBUG})"
  COCOS_EXIT=0
  "$COCOS_BIN" --project "$PROJECT_DIR" --build "platform=web-mobile;debug=${BUILD_DEBUG}" || COCOS_EXIT=$?

  # Cocos often exits non-zero (e.g. 36) after web-mobile finishes when helper
  # processes die (mach_port_rendezvous). Treat a real build output as success.
  if [[ -d "$BUILD_OUT" && -f "$BUILD_OUT/index.html" ]]; then
    if [[ "$COCOS_EXIT" -ne 0 ]]; then
      echo "Warning: Cocos exited $COCOS_EXIT but web-mobile is present; continuing." >&2
    fi
    echo "Done: $BUILD_OUT"
    echo "PROJECT_DIR=$PROJECT_DIR"
    exit 0
  fi

  if [[ "$COCOS_EXIT" -ne 0 ]]; then
    echo "Cocos build failed (exit $COCOS_EXIT) and web-mobile is missing." >&2
    exit "$COCOS_EXIT"
  fi
  echo "Cocos finished but web-mobile is missing: $BUILD_OUT" >&2
  exit 1
fi

if [[ "$FORCE" == "--force" ]]; then
  echo "Cocos Creator not found. Set GAMECENTER_COCOS_CREATOR_BIN in ops/scripts/gamecenter-local.env" >&2
  exit 1
fi

if [[ -d "$BUILD_OUT" && -n "$(ls -A "$BUILD_OUT" 2>/dev/null || true)" ]]; then
  echo "Reuse existing build at $BUILD_OUT"
  echo "PROJECT_DIR=$PROJECT_DIR"
  exit 0
fi

echo "No Cocos binary and no existing build." >&2
exit 1
