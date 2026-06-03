#!/usr/bin/env bash
# Best-effort check that DATABASE_URL host is reachable
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/../.." && pwd)"
ENV_FILE="$ROOT/src/backend/.env"

[[ -f "$ENV_FILE" ]] || exit 0

url="$(grep -E '^DATABASE_URL=' "$ENV_FILE" | head -1 | cut -d= -f2-)"
url="${url#\"}"; url="${url%\"}"
url="${url#\'}"; url="${url%\'}"
[[ -z "$url" ]] && exit 0

rest="${url#*://}"
rest="${rest#*@}"
hostport="${rest%%/*}"
host="${hostport%%:*}"
port="${hostport##*:}"
[[ "$hostport" == "$host" ]] && port=3306

[[ "$host" != "localhost" && "$host" != "127.0.0.1" ]] && exit 0

if command -v nc >/dev/null 2>&1; then
  nc -z "$host" "$port" 2>/dev/null && exit 0
elif (echo >/dev/tcp/"$host"/"$port") 2>/dev/null; then
  exit 0
fi

echo "MySQL is not listening on ${host}:${port}." >&2
echo "  Start: make db-mysql-dev" >&2
echo "  Or update DATABASE_URL in src/backend/.env" >&2
echo "  Skip Docker MySQL: MCHAT_SETUP_MYSQL=0 make setup" >&2
exit 0
