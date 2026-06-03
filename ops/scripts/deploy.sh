#!/bin/bash
# mchat deploy helper
# Usage: bash ops/scripts/deploy.sh [dev|prod|stop]

set -euo pipefail

MODE="${1:-dev}"
PROJECT_DIR="$(cd "$(dirname "$0")/../.." && pwd)"

echo "mchat deploy (mode: $MODE)"
cd "$PROJECT_DIR"

case "$MODE" in
  dev)
    if [ ! -f ops/docker/.env ]; then
      echo "Missing ops/docker/.env — creating from example..."
      cp ops/docker/.env.example ops/docker/.env
      echo "Edit ops/docker/.env and re-run"
      exit 1
    fi
    docker compose -f ops/docker/docker-compose.yml build
    docker compose -f ops/docker/docker-compose.yml up -d
    echo ""
    echo "Dev stack up:"
    echo "  Admin:  http://localhost:5173/admin"
    echo "  API:    http://localhost:3001/docs"
    echo "  Logs:   docker compose -f ops/docker/docker-compose.yml logs -f"
    ;;

  prod)
    if [ ! -f ops/docker/.env.production ]; then
      echo "Missing ops/docker/.env.production"
      exit 1
    fi
    docker compose -f ops/docker/docker-compose.prod.yml --env-file ops/docker/.env.production build
    docker compose -f ops/docker/docker-compose.prod.yml --env-file ops/docker/.env.production up -d
    echo "Production stack up"
    ;;

  stop)
    docker compose -f ops/docker/docker-compose.yml down
    docker compose -f ops/docker/docker-compose.prod.yml down 2>/dev/null || true
    echo "Stopped"
    ;;

  *)
    echo "Usage: bash ops/scripts/deploy.sh [dev|prod|stop]"
    exit 1
    ;;
esac
