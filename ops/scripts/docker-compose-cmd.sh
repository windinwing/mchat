#!/usr/bin/env bash
set -euo pipefail

if [[ -n "${MCHAT_DOCKER:-}" ]]; then
  # shellcheck disable=SC2086
  exec ${MCHAT_DOCKER} compose "$@"
fi

if docker info >/dev/null 2>&1; then
  exec docker compose "$@"
fi

if sudo docker info >/dev/null 2>&1; then
  echo "Using sudo docker (recommended: sudo usermod -aG docker \"\$USER\" then re-login)" >&2
  exec sudo docker compose "$@"
fi

echo "Cannot connect to Docker daemon." >&2
echo "  sudo usermod -aG docker \"\$USER\" && re-login" >&2
echo "  or: sudo make setup / sudo make docker-up-lite" >&2
exit 1
