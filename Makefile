.PHONY: help install install-git-hooks dev dev-worker dev-stop cloud cloud-stop worker dev-backend deploy-core deploy-cloud dev-frontend build start docker-up docker-down docker-build clean test lint coverage db-init db-seed fmt

help: ## Show this help
	@grep -E '^[a-zA-Z_-]+:.*?## .*$$' $(MAKEFILE_LIST) | sort | awk 'BEGIN {FS = ":.*?## "}; {printf "\033[36m%-20s\033[0m %s\n", $$1, $$2}'

install: ## Install all dependencies
	cd src/backend && python3 -m venv venv && source venv/bin/activate && pip install -r requirements.txt && pip install pytest pytest-asyncio pytest-cov httpx aiosqlite
	cd src/frontend && npm install

install-git-hooks: ## GitHub(origin) only allows local dev -> dev/main
	@bash ops/scripts/install-git-hooks.sh

dev: ## Start Core dev servers (app.main — no portal/templates API)
	@bash ops/scripts/dev-start.sh

dev-worker: ## Start Core dev servers + worker (worker default disabled otherwise)
	@MCHAT_DEV_WITH_WORKER=1 bash ops/scripts/dev-start.sh

dev-stop: ## Stop processes on ports 3001 and 5173
	@bash ops/scripts/dev-stop.sh

dev-db: ## Start local dev MySQL (Docker)
	@bash ops/scripts/ensure-dev-mysql.sh

cloud: ## Start Cloud (Core + signup/portal/templates) dev servers
	@bash ops/scripts/cloud-start.sh

cloud-stop: ## Stop Cloud dev servers (same as dev-stop)
	@bash ops/scripts/cloud-stop.sh

worker: ## Run independent background worker (default disabled)
	cd src/backend && source venv/bin/activate && python -m app.worker.main

deploy-core: ## Deploy Core to 192.169.177.210 (http://mchat.chat)
	@bash ops/scripts/deploy-remote-core.sh

deploy-cloud: ## Deploy Cloud to 10.98.8.15 (https://mchat.9235.net)
	@bash ops/scripts/deploy-remote-cloud.sh

dev-backend: ## Start backend only (frees port 3001 first)
	@bash ops/scripts/dev-stop.sh 2>/dev/null || true
	@lsof -ti:3001 | xargs kill -9 2>/dev/null || true
	cd src/backend && source venv/bin/activate && python -m uvicorn app.main:app --reload --host 0.0.0.0 --port 3001

dev-frontend: ## Start frontend dev server only
	cd src/frontend && npm run dev

build: ## Build frontend for production
	cd src/frontend && npm run build

docker-up: ## Start all services via Docker Compose
	docker compose -f ops/docker/docker-compose.yml up -d

docker-up-lite: ## Start minimal services (MySQL + Backend + Frontend, no Milvus)
	docker compose -f ops/docker/docker-compose.lite.yml up -d

db-mysql-dev: ## Start local dev MySQL only (port 3306)
	docker compose -f ops/docker/docker-compose.dev.yml up -d

docker-down: ## Stop all Docker services
	docker compose -f ops/docker/docker-compose.yml down

docker-build: ## Build Docker images
	docker compose -f ops/docker/docker-compose.yml build

docker-logs: ## View Docker logs
	docker compose -f ops/docker/docker-compose.yml logs -f

clean: ## Clean build artifacts
	rm -rf src/backend/__pycache__ src/backend/app/**/__pycache__
	rm -rf src/frontend/dist src/frontend/node_modules
	rm -rf *.log logs/*.log
	find . -name "*.pyc" -delete
	find . -name "*.tsbuildinfo" -delete
	find . -name "__pycache__" -type d -delete

test: ## Run backend tests
	cd src/backend && python -m pytest ../../tests/ -v

test-cov: ## Run tests with coverage report
	cd src/backend && python -m pytest ../../tests/ -v --cov=app --cov-report=term-missing

lint: ## Run linters
	cd src/backend && ruff check app/ 2>/dev/null || echo "ruff not installed"
	cd src/frontend && npm run lint 2>/dev/null || echo "ESLint not configured"

fmt: ## Format code
	cd src/backend && ruff format app/ 2>/dev/null || echo "ruff not installed"
	cd src/frontend && npx prettier --write "src/**/*.{ts,tsx,css}" 2>/dev/null || echo "prettier not installed"

db-init: ## Initialize database tables
	cd src/backend && python -c "from app.cli import _cmd_db; import asyncio, argparse; asyncio.run(_cmd_db(argparse.Namespace(db_action='init')))"

db-migrate: ## Apply schema patches (new columns, etc.)
	cd src/backend && source venv/bin/activate && python -m app.cli db migrate

db-seed: ## Seed database with default data
	cd src/backend && python -c "from app.cli import _cmd_db; import asyncio, argparse; asyncio.run(_cmd_db(argparse.Namespace(db_action='seed')))"
