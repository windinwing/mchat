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

read_project_cocos_version() {
  local project_dir="${1:-}"
  [[ -n "$project_dir" ]] || return 0
  local pj="$project_dir/project.json"
  local pkg="$project_dir/package.json"
  if [[ -f "$pj" ]]; then
    grep '"version"' "$pj" 2>/dev/null | head -1 | sed -E 's/.*"version"[[:space:]]*:[[:space:]]*"([^"]+)".*/\1/'
    return 0
  fi
  if [[ -f "$pkg" ]]; then
    local py=""
    for py in python python3; do
      command -v "$py" >/dev/null 2>&1 || continue
      "$py" -c "import json; d=json.load(open('${pkg//\'/\\\'}')); c=d.get('creator') or {}; print(str(c.get('version','')).strip())" 2>/dev/null && return 0
    done
  fi
}

find_cocos_bins_for_major() {
  local major="${1:-3}"
  local preferred_ver="${2:-}"

  if [[ -n "$preferred_ver" ]]; then
    local exact_candidates=(
      "/c/ProgramData/cocos/editors/Creator/${preferred_ver}/CocosCreator.exe"
      "/Applications/Cocos/Creator/${preferred_ver}/CocosCreator.app/Contents/MacOS/CocosCreator"
      "/Applications/CocosCreator/CocosCreator.app/Contents/MacOS/CocosCreator"
    )
    local candidate
    for candidate in "${exact_candidates[@]}"; do
      if [[ -x "$candidate" || -f "$candidate" ]]; then
        echo "$candidate"
        return 0
      fi
    done
  fi

  local pattern="${major}.*"
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
    done < <(find "$cocos_root" -maxdepth 1 -mindepth 1 -type d -name "$pattern" 2>/dev/null | sort -Vr)
  fi

  local win_roots=(
    "/c/ProgramData/cocos/editors/Creator"
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
    done < <(find "$win_root" -maxdepth 1 -mindepth 1 -type d -name "$pattern" 2>/dev/null | sort -Vr)
  done
  return 1
}

discover_cocos_bin() {
  local project_dir="${1:-}"

  local project_ver major preferred
  project_ver="$(read_project_cocos_version "$project_dir")"
  if [[ -n "$project_ver" ]]; then
    major="${project_ver%%.*}"
    if [[ "$major" == "2" ]]; then
      preferred="${GAMECENTER_COCOS_2_VERSION:-2.4.15}"
    elif [[ "$major" == "3" ]]; then
      preferred="${GAMECENTER_COCOS_3_VERSION:-3.8.8}"
    else
      preferred="$project_ver"
    fi
    matched="$(find_cocos_bins_for_major "$major" "$preferred" || true)"
    if [[ -n "$matched" ]]; then
      echo "$matched"
      return 0
    fi
  fi

  if [[ -n "${GAMECENTER_COCOS_CREATOR_BIN:-}" && ( -x "${GAMECENTER_COCOS_CREATOR_BIN}" || -f "${GAMECENTER_COCOS_CREATOR_BIN}" ) ]]; then
    echo "${GAMECENTER_COCOS_CREATOR_BIN}"
    return 0
  fi
  if [[ -n "${COCOS_CREATOR_BIN:-}" && ( -x "${COCOS_CREATOR_BIN}" || -f "${COCOS_CREATOR_BIN}" ) ]]; then
    echo "${COCOS_CREATOR_BIN}"
    return 0
  fi

  matched="$(find_cocos_bins_for_major 3 "${GAMECENTER_COCOS_3_VERSION:-3.8.8}" || true)"
  if [[ -n "$matched" ]]; then
    echo "$matched"
    return 0
  fi
  matched="$(find_cocos_bins_for_major 2 "${GAMECENTER_COCOS_2_VERSION:-2.4.15}" || true)"
  if [[ -n "$matched" ]]; then
    echo "$matched"
    return 0
  fi

  local candidate
  for candidate in \
    "/Applications/Cocos/Creator/3.8.8/CocosCreator.app/Contents/MacOS/CocosCreator" \
    "/Applications/Cocos/Creator/2.4.15/CocosCreator.app/Contents/MacOS/CocosCreator" \
    "/c/ProgramData/cocos/editors/Creator/3.8.8/CocosCreator.exe" \
    "/c/Program Files/Cocos/Creator/3.8.8/CocosCreator.exe" \
    "/c/Program Files/Cocos/Creator/2.4.15/CocosCreator.exe"; do
    if [[ -x "$candidate" || -f "$candidate" ]]; then
      echo "$candidate"
      return 0
    fi
  done
  return 1
}

COCOS_BIN="$(discover_cocos_bin "$PROJECT_DIR" || true)"
BUILD_OUT="$PROJECT_DIR/build/web-mobile"
# debug=true embeds showFPS in web-mobile (application.js). Use false for playable builds.
BUILD_DEBUG="${GAMECENTER_BUILD_DEBUG:-false}"

if [[ -n "$COCOS_BIN" && ( -x "$COCOS_BIN" || -f "$COCOS_BIN" ) ]]; then
  PROJECT_VER="$(read_project_cocos_version "$PROJECT_DIR")"
  COCOS_MAJOR="${PROJECT_VER%%.*}"
  if [[ "$COCOS_MAJOR" == "2" ]]; then
    echo "Building with local Cocos 2.x: $COCOS_BIN (version=${PROJECT_VER:-unknown})"
    COCOS_EXIT=0
    # Cocos 2.x build-worker uses WebGL (ANGLE→D3D on Windows). In headless / build
    # contexts D3D device creation can fail, making canvas.getContext('webgl') return
    # null → "Cannot read property 'getParameter' of null".
    # Force CPU-based WebGL via SwiftShader so the build-worker can pack textures / sprites.
    GAMECENTER_2X_SWIFTSHADER="${GAMECENTER_2X_SWIFTSHADER:-1}"
    if [[ "${GAMECENTER_2X_SWIFTSHADER}" == "1" ]]; then
      echo "SwiftShader mode: forcing CPU-based WebGL (set GAMECENTER_2X_SWIFTSHADER=0 to disable)"
      # Electron 8.x may not read ELECTRON_EXTRA_LAUNCH_ARGS — pass GPU flags as
      # CocosCreator.exe CLI args directly (Electron parses them before app args).
      "$COCOS_BIN" \
        --use-gl=swiftshader --ignore-gpu-blocklist --disable-gpu-sandbox \
        --path "$PROJECT_DIR" --build "platform=web-mobile" || COCOS_EXIT=$?
    else
      "$COCOS_BIN" --path "$PROJECT_DIR" --build "platform=web-mobile" || COCOS_EXIT=$?
    fi
  else
    echo "Building with local Cocos: $COCOS_BIN (debug=${BUILD_DEBUG})"
    COCOS_EXIT=0
    "$COCOS_BIN" --project "$PROJECT_DIR" --build "platform=web-mobile;debug=${BUILD_DEBUG}" || COCOS_EXIT=$?
  fi

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
