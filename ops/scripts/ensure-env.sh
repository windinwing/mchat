#!/usr/bin/env bash
# Shared lite MySQL env helpers (does not export NODE_ENV from docker .env)
set -euo pipefail

_env_script="${BASH_SOURCE[0]:-$0}"
ROOT="$(cd "$(dirname "$_env_script")/../.." && pwd)"

runtime_user() {
  echo "${SUDO_USER:-${USER:-$(id -un)}}"
}

fix_file_ownership() {
  local f=$1
  local u owner
  u="$(runtime_user)"
  [[ -f "$f" ]] || return 0
  [[ "$u" == "root" ]] && return 0
  if [[ -r "$f" && -w "$f" ]]; then
    owner=$(stat -c '%U' "$f" 2>/dev/null || stat -f '%Su' "$f" 2>/dev/null || echo "")
    [[ "$owner" != "root" ]] && return 0
  fi
  if [[ "$(id -un)" == "root" ]]; then
    chown "$u:$u" "$f"
    return 0
  fi
  if sudo chown "$u:$u" "$f" 2>/dev/null; then
    echo "Fixed ownership: $f -> $u"
    return 0
  fi
  echo "Cannot read/write $f (often created by sudo make)"
  echo "Fix: sudo chown $u:$u $f"
  return 1
}

fix_env_permissions() {
  fix_file_ownership "$ROOT/ops/docker/.env" || return 1
  fix_file_ownership "$ROOT/src/backend/.env" 2>/dev/null || true
}

fix_dir_ownership() {
  local d=$1
  local u owner
  u="$(runtime_user)"
  [[ -e "$d" ]] || return 0
  [[ "$u" == "root" ]] && return 0

  owner=$(stat -c '%U' "$d" 2>/dev/null || stat -f '%Su' "$d" 2>/dev/null || echo "")
  if [[ -w "$d" && "$owner" != "root" ]]; then
    return 0
  fi

  if [[ "$(id -un)" == "root" ]]; then
    chown -R "$u:$u" "$d"
    echo "Fixed ownership: $d"
    return 0
  fi
  if sudo chown -R "$u:$u" "$d" 2>/dev/null; then
    echo "Fixed ownership: $d -> $u"
    return 0
  fi
  echo "Removing unfixable $d (root-owned; will recreate)..."
  sudo rm -rf "$d" || {
    echo "Need: sudo rm -rf $d"
    return 1
  }
}

fix_install_permissions() {
  fix_env_permissions 2>/dev/null || true
  fix_dir_ownership "$ROOT/src/backend/venv"
  fix_dir_ownership "$ROOT/src/frontend/node_modules"
}

force_sync_backend_env() {
  ensure_docker_env_file
  ensure_backend_env_file
  read_mysql_env
  sync_backend_database_url
}

read_mysql_env() {
  MYSQL_PORT=3307
  MYSQL_USER=mchat
  MYSQL_PASSWORD=mchat123
  MYSQL_DATABASE=mchat
  MYSQL_ROOT_PASSWORD=root123
  FRONTEND_PORT=5173
  BACKEND_PORT=3001
  ADMIN_USERNAME=admin
  ADMIN_PASSWORD=admin123

  [[ -f "$ROOT/ops/docker/.env" ]] || return 0
  if [[ ! -r "$ROOT/ops/docker/.env" ]]; then
    fix_file_ownership "$ROOT/ops/docker/.env" || return 0
  fi

  local line key val
  while IFS= read -r line || [[ -n "$line" ]]; do
    line="${line%%#*}"
    line="${line#"${line%%[![:space:]]*}"}"
    [[ -z "$line" ]] && continue
    [[ "$line" != MYSQL_*=* && "$line" != FRONTEND_PORT=* && "$line" != BACKEND_PORT=* \
      && "$line" != ADMIN_USERNAME=* && "$line" != ADMIN_PASSWORD=* ]] && continue
    key="${line%%=*}"
    val="${line#*=}"
    val="${val#\"}"; val="${val%\"}"
    val="${val#\'}"; val="${val%\'}"
    printf -v "$key" '%s' "$val"
  done < "$ROOT/ops/docker/.env"
}

ensure_docker_env_file() {
  if [[ ! -f "$ROOT/ops/docker/.env" ]]; then
    cp "$ROOT/ops/docker/.env.example" "$ROOT/ops/docker/.env"
    echo "Created ops/docker/.env"
  fi
  fix_file_ownership "$ROOT/ops/docker/.env"
}

ensure_backend_env_file() {
  if [[ ! -f "$ROOT/src/backend/.env" ]]; then
    cp "$ROOT/src/backend/.env.example" "$ROOT/src/backend/.env"
    echo "Created src/backend/.env"
  fi
  fix_file_ownership "$ROOT/src/backend/.env"
}

sed_inplace() {
  local expr=$1 file=$2
  if sed -i.bak "$expr" "$file" 2>/dev/null; then
    rm -f "${file}.bak"
  else
    sed -i '' "$expr" "$file"
  fi
}

sync_backend_database_url() {
  read_mysql_env
  local env_file="$ROOT/src/backend/.env"
  [[ -f "$env_file" ]] || return 0
  local url="mysql+aiomysql://${MYSQL_USER}:${MYSQL_PASSWORD}@localhost:${MYSQL_PORT}/${MYSQL_DATABASE}"
  if grep -q '^DATABASE_URL=' "$env_file"; then
    sed_inplace "s|^DATABASE_URL=.*|DATABASE_URL=${url}|" "$env_file"
  else
    echo "DATABASE_URL=${url}" >> "$env_file"
  fi
}

configure_docker_cmd() {
  if [[ -n "${MCHAT_DOCKER:-}" ]]; then
    return 0
  fi
  if docker info >/dev/null 2>&1; then
    return 0
  fi
  export MCHAT_DOCKER="sudo docker"
  echo "Docker requires sudo (recommended: sudo usermod -aG docker \"\$USER\" then re-login)"
}

docker_compose() {
  configure_docker_cmd
  bash "$ROOT/ops/scripts/docker-compose-cmd.sh" "$@"
}
