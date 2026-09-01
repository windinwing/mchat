#!/usr/bin/env bash
# Prep local env for per-user Docker sidecar + tenant skill testing.
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/../.." && pwd)"
cd "$ROOT"

echo "== MChat workspace container test prep =="
echo "Branch: $(git branch --show-current 2>/dev/null || echo unknown)"
echo ""

if ! command -v docker >/dev/null 2>&1; then
  echo "❌ docker CLI not found. Install Docker Desktop and retry."
  exit 1
fi
if ! docker info >/dev/null 2>&1; then
  echo "❌ Docker daemon not running. Start Docker Desktop, then rerun this script."
  exit 1
fi
echo "✓ Docker daemon OK"

IMAGE="${WORKSPACE_CONTAINER_IMAGE:-python:3.12-slim}"
echo "→ Pulling sidecar image: $IMAGE"
docker pull "$IMAGE"

bash "$ROOT/ops/scripts/ensure-dev-mysql.sh"
bash "$ROOT/ops/scripts/verify-mysql.sh" || exit 1
echo "✓ MySQL dev OK"

TENANT_ROOT="$ROOT/data/tenants"
mkdir -p "$TENANT_ROOT"
echo "✓ Tenant root: $TENANT_ROOT"

ENV_FILE="$ROOT/src/backend/.env"
if ! grep -q '^WORKSPACE_CONTAINER_ENABLED=true' "$ENV_FILE" 2>/dev/null; then
  echo "⚠ WORKSPACE_CONTAINER_ENABLED not true in src/backend/.env — enable before testing."
else
  echo "✓ WORKSPACE_CONTAINER_ENABLED=true"
fi

echo ""
echo "Next:"
echo "  1. make dev          # Core admin"
echo "  2. Open http://localhost:5173/admin  (admin / admin123)"
echo "  3. /admin/workspace  → grant container + set sidecar limits for test user"
echo "  4. /admin/channels   → Pro plan + workspace_mode=container for user's channel"
echo "  5. Login as test user → /admin/skills → create / edit tenant skills"
echo "  6. Verify: docker ps --filter label=mchat.workspace=true"
echo ""
