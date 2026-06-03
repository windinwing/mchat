#!/usr/bin/env bash
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/../.." && pwd)"
ENV_FILE="$ROOT/src/backend/.env"

[[ -f "$ENV_FILE" ]] || { echo "Missing src/backend/.env — run: make setup"; exit 1; }

url="$(grep -E '^DATABASE_URL=' "$ENV_FILE" | head -1 | cut -d= -f2-)"
url="${url#\"}"; url="${url%\"}"

if [[ -z "$url" ]]; then
  echo "DATABASE_URL is not set"
  exit 1
fi

cd "$ROOT/src/backend"
[[ -d venv ]] || { echo "Missing venv — run: make setup"; exit 1; }
# shellcheck disable=SC1091
source venv/bin/activate

python - <<'PY' "$url"
import asyncio, sys
from sqlalchemy.ext.asyncio import create_async_engine
from sqlalchemy import text

async def main():
    url = sys.argv[1]
    eng = create_async_engine(url)
    try:
        async with eng.connect() as c:
            await c.execute(text("SELECT 1"))
        print("MySQL OK:", url.split("@")[-1])
    except Exception as e:
        print("MySQL connection failed:", e, file=sys.stderr)
        print("", file=sys.stderr)
        print("Try:", file=sys.stderr)
        print("  1) make setup", file=sys.stderr)
        print("  2) make db-docker-reset-lite && make setup", file=sys.stderr)
        print("  3) Align DATABASE_URL in src/backend/.env with ops/docker/.env", file=sys.stderr)
        sys.exit(1)
    finally:
        await eng.dispose()

asyncio.run(main())
PY
