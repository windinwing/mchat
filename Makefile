# Use bash so recipes may `source venv/bin/activate` (dash lacks `source`).
SHELL := /bin/bash

BACKEND_DIR := src/backend
WITH_VENV := bash ops/scripts/with-venv.sh
FIND_PYTHON := bash ops/scripts/find-python.sh
# Fallback when ops/scripts/docker-compose-cmd.sh not synced yet
DOCKER_COMPOSE := $(shell if [ -x ops/scripts/docker-compose-cmd.sh ] 2>/dev/null || [ -f ops/scripts/docker-compose-cmd.sh ]; then echo 'bash ops/scripts/docker-compose-cmd.sh'; elif docker info >/dev/null 2>&1; then echo 'docker compose'; else echo 'sudo docker compose'; fi)
DOCKER_LITE_ENV := -f ops/docker/docker-compose.lite.yml --env-file ops/docker/.env

.PHONY: help install setup install-git-hooks dev dev-worker dev-stop cloud cloud-stop worker dev-backend deploy-core deploy-cloud dev-frontend build start docker-up docker-down docker-build clean reset-fresh test lint coverage db-init db-seed fmt patent-skills-env patent-skills-reload patent-skills-prune test-patent-showcase env-hint

help: ## Show this help
	@grep -E '^[a-zA-Z_-]+:.*?## .*$$' $(MAKEFILE_LIST) | sort | awk 'BEGIN {FS = ":.*?## "}; {printf "\033[36m%-20s\033[0m %s\n", $$1, $$2}'

install: ## Install all dependencies (backend venv + frontend npm + mchat CLI)
	@bash ops/scripts/fix-install-permissions.sh
	@PY=$$($(FIND_PYTHON)); echo "→ Using $$PY ($$($$PY -V))"; \
	cd $(BACKEND_DIR) && "$$PY" -m venv venv
	$(WITH_VENV) pip install -U pip
	$(WITH_VENV) pip install -r requirements.txt
	$(WITH_VENV) pip install pytest pytest-asyncio pytest-cov httpx aiosqlite
	$(WITH_VENV) pip install -e .
	@bash ops/scripts/frontend-install.sh
	@$(MAKE) --no-print-directory env-hint

env-hint: ## Print how to enable short `mchat` command in shell
	@echo ""
	@echo "✓ Install done. For short commands in this shell:"
	@echo "    source scripts/env.sh"
	@echo "    mchat run"
	@echo "  Or without sourcing: ./bin/mchat run"
	@echo ""

setup: ## First-time setup: MySQL + deps + db init (auto sudo docker if needed)
	@bash ops/scripts/setup.sh

setup-no-db: ## Setup without Docker MySQL (configure DATABASE_URL yourself)
	@MCHAT_SETUP_MYSQL=0 bash ops/scripts/setup.sh

reset-fresh: ## Wipe Docker lite + venv/node_modules/.env for clean re-test
	@bash ops/scripts/reset-fresh.sh

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
	$(WITH_VENV) python -m app.worker.main

deploy-core: ## Deploy Core (set MCHAT_DEPLOY_REMOTE=user@host)
	@test -n "$${MCHAT_DEPLOY_REMOTE:-}" || { echo "Set MCHAT_DEPLOY_REMOTE=user@host"; exit 1; }
	@bash ops/scripts/deploy-remote-core.sh "$${MCHAT_DEPLOY_REMOTE}"

deploy-cloud: ## Deploy Cloud (set MCHAT_DEPLOY_REMOTE=user@host)
	@test -n "$${MCHAT_DEPLOY_REMOTE:-}" || { echo "Set MCHAT_DEPLOY_REMOTE=user@host"; exit 1; }
	@bash ops/scripts/deploy-remote-cloud.sh "$${MCHAT_DEPLOY_REMOTE}"

dev-backend: ## Start backend only (frees port 3001 first)
	@bash ops/scripts/dev-stop.sh 2>/dev/null || true
	@lsof -ti:3001 | xargs kill -9 2>/dev/null || true
	$(WITH_VENV) python -m uvicorn app.main:app --reload --host 0.0.0.0 --port 3001

dev-frontend: ## Start frontend dev server only
	cd src/frontend && npm run dev

build: ## Build frontend for production
	cd src/frontend && npm run build

docker-up: ## Start all services via Docker Compose
	docker compose -f ops/docker/docker-compose.yml up -d

docker-up-lite: ## Docker lite stack: .env + MySQL + build + start
	@bash ops/scripts/docker-lite-up.sh

docker-down-lite: ## Stop Docker lite stack
	@$(DOCKER_COMPOSE) $(DOCKER_LITE_ENV) down

docker-logs-lite: ## Tail Docker lite logs
	@$(DOCKER_COMPOSE) $(DOCKER_LITE_ENV) logs -f --tail=100

db-mysql-dev: ## Start lite MySQL only
	@$(DOCKER_COMPOSE) $(DOCKER_LITE_ENV) up -d mysql

db-mysql-dev-stop: ## Stop lite MySQL container
	@$(DOCKER_COMPOSE) $(DOCKER_LITE_ENV) stop mysql

db-docker-reset-lite: ## Reset lite stack MySQL volume (fixes password mismatch)
	@$(DOCKER_COMPOSE) $(DOCKER_LITE_ENV) down -v
	@echo "→ Lite MySQL volume removed; next up uses passwords from ops/docker/.env"

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
	$(WITH_VENV) python -m pytest ../../tests/ -v

test-cov: ## Run tests with coverage report
	$(WITH_VENV) python -m pytest ../../tests/ -v --cov=app --cov-report=term-missing

lint: ## Run linters
	cd $(BACKEND_DIR) && ruff check app/ 2>/dev/null || echo "ruff not installed"
	cd src/frontend && npm run lint 2>/dev/null || echo "ESLint not configured"

fmt: ## Format code
	cd $(BACKEND_DIR) && ruff format app/ 2>/dev/null || echo "ruff not installed"
	cd src/frontend && npx prettier --write "src/**/*.{ts,tsx,css}" 2>/dev/null || echo "prettier not configured"

db-init: ## Initialize database tables
	$(WITH_VENV) python -c "from app.cli import _cmd_db; import asyncio, argparse; asyncio.run(_cmd_db(argparse.Namespace(db_action='init')))"

db-migrate: ## Apply schema patches (new columns, etc.)
	$(WITH_VENV) python -m app.cli db migrate

db-seed: ## Seed database with default data
	$(WITH_VENV) python -c "from app.cli import _cmd_db; import asyncio, argparse; asyncio.run(_cmd_db(argparse.Namespace(db_action='seed')))"

PATENT_SKILLS_DIR ?= $(HOME)/dev/skills/patents

patent-skills-env: ## Print/write .env snippet for external patent skills repo
	@PATENT_SKILLS_DIR="$(PATENT_SKILLS_DIR)" bash scripts/setup-patent-skills-env.sh $(if $(WRITE),--write,)

patent-skills-prune: ## Remove patent-* copies from mchat/skills (use EXTRA_SKILLS_DIRS)
	@bash scripts/prune-local-patent-skills.sh

patent-skills-reload: ## Reload skills from SKILLS_DIR + EXTRA_SKILLS_DIRS into DB
	EXTRA_SKILLS_DIRS="$(PATENT_SKILLS_DIR)" $(WITH_VENV) python ../../scripts/reload-patent-skills.py

test-patent-showcase: ## Run patent workflow + report unit tests
	cd $(BACKEND_DIR) && EXTRA_SKILLS_DIRS="$(PATENT_SKILLS_DIR)" PYTHONPATH=. $(WITH_VENV) python -m pytest ../../tests/unit/test_patent_workflow_showcase.py ../../tests/unit/test_patent_report_skill.py ../../tests/unit/test_workflow_graph.py -q
