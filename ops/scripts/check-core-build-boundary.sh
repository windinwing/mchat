#!/usr/bin/env bash
# Verify that a completed Core frontend build did not pull in Cloud-only entrypoints.
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/../.." && pwd)"
FRONTEND="$ROOT/src/frontend"
DIST="$FRONTEND/dist"

if ! grep -q 'src="/src/main.tsx"' "$FRONTEND/index.html"; then
  echo "ERROR: tracked index.html must use the Core main.tsx entry." >&2
  exit 1
fi
if grep -q 'main-portal.tsx' "$FRONTEND/index.html"; then
  echo "ERROR: tracked index.html points at the Cloud entry." >&2
  exit 1
fi
if [[ ! -f "$DIST/index.html" ]]; then
  echo "ERROR: Core build output is missing dist/index.html." >&2
  exit 1
fi
if grep -q 'main-portal' "$DIST/index.html"; then
  echo "ERROR: Core dist/index.html points at a Cloud entry." >&2
  exit 1
fi

# The Vite core-boundary plugin checks the Rollup module graph. This final
# artifact check catches accidental Cloud-named entry chunks as a second guard.
if find "$DIST" -type f \( \
  -name '*main-portal*' -o \
  -name '*routes-portal*' -o \
  -name '*AppPortal*' -o \
  -name 'portalApi-*' \
\) -print -quit | grep -q .; then
  echo "ERROR: Core build emitted a Cloud-only chunk." >&2
  exit 1
fi

echo "Core build boundary OK"
