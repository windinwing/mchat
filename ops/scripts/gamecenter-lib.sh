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
