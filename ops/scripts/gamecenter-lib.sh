#!/usr/bin/env bash
# Shared helpers for GameCenter local pipeline scripts.

gc_resolve_nested_project_dir() {
  local outer="${1:-}"
  if [[ -z "$outer" || ! -d "$outer" ]]; then
    return 1
  fi
  if [[ -f "$outer/project.json" || -f "$outer/package.json" ]]; then
    printf '%s\n' "$outer"
    return 0
  fi
  local child
  shopt -s nullglob
  for child in "$outer"/*; do
    [[ -d "$child" ]] || continue
    if [[ -f "$child/project.json" || -f "$child/package.json" ]]; then
      printf '%s\n' "$child"
      return 0
    fi
  done
  shopt -u nullglob
  printf '%s\n' "$outer"
}

# Derive the local outer slug dir from a remote outer path.
# Mirrors the pipeline's LOCAL_OUTER logic: maps ${REMOTE_ROOT}/src/<rel> → $LOCAL_GC/src/<rel>.
# Usage: gc_local_outer_for_remote <remote_outer> [remote_root] [slug]
gc_local_outer_for_remote() {
  local remote_outer="${1:-}"
  local remote_root="${2:-${REMOTE_GAMECENTER_ROOT:-/opt/xiaoxiao/gamecenter}}"
  local local_gc="${LOCAL_GAMECENTER:-$HOME/dev/gamecenter-server}"
  local remote_parent="${REMOTE_PROJECT_PARENT:-src}"
  local slug="${3:-}"

  if [[ -n "$remote_outer" && "$remote_outer" == "${remote_root}/src/"* ]]; then
    local rel="${remote_outer#${remote_root}/src/}"
    printf '%s\n' "$local_gc/src/$rel"
  elif [[ -n "$slug" ]]; then
    printf '%s\n' "$local_gc/$remote_parent/$slug"
  else
    return 1
  fi
}

# Outer slug directory for rsync (walk up from nested Cocos project dir).
gc_slug_outer_from_project_dir() {
  local project_dir="${1:-}"
  local slug="${2:-}"
  local remote_root="${3:-}"
  if [[ -z "$project_dir" || -z "$slug" ]]; then
    return 1
  fi
  local outer="$project_dir"
  while [[ "$(basename "$outer")" != "$slug" ]]; do
    local parent
    parent="$(dirname "$outer")"
    if [[ "$outer" == "$parent" ]]; then
      return 1
    fi
    if [[ -n "$remote_root" && "$parent" == "$remote_root" ]]; then
      return 1
    fi
    outer="$parent"
  done
  printf '%s\n' "$outer"
}

# Resolve remote nested Cocos project dir for a slug (requires ssh + mchat on server).
gc_remote_project_dir() {
  local host_raw="${1:-}"
  local slug="${2:-}"
  local remote_mchat="${3:-/opt/xiaoxiao/mchat}"
  local ssh_user="${SSH_USER:-xiaoxiao}"
  local ssh_target resolver

  if [[ -z "$host_raw" || -z "$slug" ]]; then
    return 1
  fi
  if [[ "$host_raw" == *@* ]]; then
    ssh_target="$host_raw"
  else
    ssh_target="${ssh_user}@${host_raw}"
  fi
  resolver="$(dirname "${BASH_SOURCE[0]}")/resolve-gamecenter-project.py"
  ssh "$ssh_target" "python3 '$remote_mchat/ops/scripts/resolve-gamecenter-project.py' '$remote_mchat' '$slug' 2>/dev/null || true"
}

# Compare one file's md5 between local path and remote ssh path; prints "match" or "DIFF".
gc_compare_file_md5() {
  local local_file="${1:-}"
  local ssh_target="${2:-}"
  local remote_file="${3:-}"

  if [[ -z "$local_file" || -z "$ssh_target" || -z "$remote_file" || ! -f "$local_file" ]]; then
    return 1
  fi
  local local_md5 remote_md5
  if command -v md5 >/dev/null 2>&1; then
    local_md5="$(md5 -q "$local_file")"
    remote_md5="$(ssh "$ssh_target" "md5 -q '$remote_file' 2>/dev/null || md5sum '$remote_file' 2>/dev/null | awk '{print \$1}'")"
  else
    local_md5="$(md5sum "$local_file" | awk '{print $1}')"
    remote_md5="$(ssh "$ssh_target" "md5sum '$remote_file' 2>/dev/null | awk '{print \$1}'")"
  fi
  if [[ -n "$local_md5" && "$local_md5" == "$remote_md5" ]]; then
    printf 'match\t%s\n' "$local_md5"
    return 0
  fi
  printf 'DIFF\tlocal=%s\tremote=%s\n' "${local_md5:-?}" "${remote_md5:-?}"
  return 1
}

# Print "project_dir<TAB>build/web-mobile" for the newest build under outer tree.
gc_find_build_output() {
  local outer="${1:-}"
  local project_dir build_out

  project_dir="$(gc_resolve_nested_project_dir "$outer")"
  build_out="$project_dir/build/web-mobile"
  if [[ -d "$build_out" && -n "$(ls -A "$build_out" 2>/dev/null || true)" ]]; then
    printf '%s\t%s\n' "$project_dir" "$build_out"
    return 0
  fi

  local index
  index="$(find "$outer" -path '*/build/web-mobile/index.html' -type f 2>/dev/null | head -1 || true)"
  if [[ -n "$index" ]]; then
    build_out="$(dirname "$index")"
    project_dir="$(dirname "$(dirname "$build_out")")"
    printf '%s\t%s\n' "$project_dir" "$build_out"
    return 0
  fi
  return 1
}

# Resolve source_relpath for a slug from the xcx workspace (e.g. "misc/cat", "puzzle/pkg0002-...").
# Requires GAMECENTER_WORKSPACE to point at the xcx checkout (default: ~/dev/xcx).
# Prints empty string on failure.
gc_local_source_relpath() {
  local slug="${1:-}"
  local workspace="${GAMECENTER_WORKSPACE:-$HOME/dev/xcx}"
  [[ -n "$slug" && -d "$workspace/gamecenter" ]] || return 1
  python3 - "$workspace" "$slug" <<'PY' 2>/dev/null || true
import sys
from pathlib import Path

workspace = Path(sys.argv[1])
slug = sys.argv[2]
sys.path.insert(0, str(workspace / "gamecenter"))
try:
    import service
    print(service.get_source_relpath(slug))
except Exception:
    pass
PY
}

# Compute GameCenter :5099 / xyx play path for a slug: /<source_relpath>/
# (e.g. "/misc/cat/", "/puzzle/pkg0002-3-x-3-8-3ts/").
# Falls back to "/<slug>/" if source_relpath cannot be resolved from the xcx workspace.
gc_play_path() {
  local slug="${1:-}"
  local relpath
  relpath="$(gc_local_source_relpath "$slug" 2>/dev/null || true)"
  if [[ -n "$relpath" ]]; then
    printf '/%s/\n' "$relpath"
  else
    printf '/%s/\n' "$slug"
  fi
}
