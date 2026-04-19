.PHONY: help install debug deploy deploy-preflight deploy-up deploy-migrate \
       deploy-bg deploy-bg-force rollback-bg \
       logs logs-app logs-frontend \
       clean lint format test migrate \
       frontend-install frontend-dev frontend-build \
       docs-serve docs-build \
       backup-db backup-db-dry-run restore-db-list

# ── Help (default target) ───────────────────────────────

help:
	@echo "Usage: make <target>"
	@echo ""
	@echo "Backend:"
	@echo "  install            Install/update UV and backend dependencies"
	@echo "  debug              Start uvicorn with hot-reload (port 8000)"
	@echo "  lint               Check backend code with ruff"
	@echo "  format             Auto-fix lint issues and format code"
	@echo "  test               Run backend pytest suite"
	@echo "  migrate            Run Alembic migrations (upgrade to head)"
	@echo ""
	@echo "Frontend:"
	@echo "  frontend-install   Install frontend npm dependencies"
	@echo "  frontend-dev       Start SvelteKit dev server"
	@echo "  frontend-build     Build frontend for production"
	@echo ""
	@echo "Docs:"
	@echo "  docs-serve         Start MkDocs dev server (port 8080)"
	@echo "  docs-build         Build documentation site (strict mode)"
	@echo ""
	@echo "Full Stack:"
	@echo "  deploy             Full deploy: preflight, build, start, migrate"
	@echo "  deploy-preflight   Validate .env, install, lint, test"
	@echo "  deploy-up          Build and start Docker services"
	@echo "  deploy-migrate     Run migrations in Docker"
	@echo "  deploy-bg          Zero-downtime blue-green deploy (interactive)"
	@echo "  deploy-bg-force    deploy-bg without the confirmation prompt"
	@echo "  rollback-bg        Flip Caddy back to the previous colour"
	@echo "  logs               Tail backend + frontend logs (Ctrl+C to exit)"
	@echo "  logs-app           Tail backend (FastAPI) logs only"
	@echo "  logs-frontend      Tail frontend (nginx) logs only"
	@echo "  clean              Tear down Docker services and remove caches"
	@echo ""
	@echo "Backups (S3-compatible, see scripts/README.md):"
	@echo "  backup-db-dry-run  Preflight the backup script (no dump, no upload)"
	@echo "  backup-db          Run a one-off ad-hoc backup (daily class)"
	@echo "  restore-db-list    List recent backups in the configured S3 bucket"

# ── Backend ──────────────────────────────────────────────

install:
	@echo "==> Installing/updating UV..."
	curl -LsSf https://astral.sh/uv/install.sh | sh
	cd backend && uv sync --all-extras

debug:
	cd backend && uv run uvicorn app.main:app --reload --host 0.0.0.0 --port 8000

lint:
	cd backend && uv run --extra dev ruff check src/ tests/
	cd backend && uv run --extra dev ruff format --check src/ tests/

format:
	cd backend && uv run --extra dev ruff check --fix src/ tests/
	cd backend && uv run --extra dev ruff format src/ tests/

test:
	cd backend && APP_ENV=testing uv run --extra dev pytest tests/ -v --tb=short

migrate:
	cd backend && uv run alembic upgrade head

# ── Frontend ─────────────────────────────────────────────

frontend-install:
	@echo "==> Updating npm to latest..."
	npm install -g npm@latest
	cd frontend && npm install

frontend-dev:
	cd frontend && npm run dev

frontend-build:
	cd frontend && npm run build

# ── Docs ─────────────────────────────────────────────────

docs-serve:
	mkdocs serve -a 127.0.0.1:8080

docs-build:
	mkdocs build --strict

# ── Full Stack ───────────────────────────────────────────

deploy: deploy-preflight deploy-up deploy-migrate
	@echo ""
	@echo "===== Deploy complete! ====="
	@echo "  Backend:  http://localhost:8000"
	@echo "  Frontend: http://localhost:3000"
	@echo "  Neo4j:    http://localhost:7474"
	@echo "  Postgres: localhost:5432"
	@echo "============================"

deploy-preflight:
	@echo "==> Checking .env file..."
	@test -f .env || { echo "ERROR: .env not found. Run: cp .env.example .env  and configure it."; exit 1; }
	@echo "==> Installing dependencies..."
	@$(MAKE) install
	@echo "==> Running lint checks..."
	@$(MAKE) lint
	@echo "==> Running tests..."
	@$(MAKE) test

deploy-up:
	@echo "==> Building and starting Docker services..."
	docker compose up --build -d --wait
	@echo "==> All services are healthy."

deploy-migrate:
	@echo "==> Running database migrations..."
	docker compose exec app uv run alembic upgrade head
	@echo "==> Migrations complete."

# ── Blue-Green Deploy (zero-downtime) ───────────────────────
# Runs the idle colour (blue/green) alongside the live one,
# flips Caddy's upstream once the new colour is healthy, then
# drains the old colour. See scripts/deploy-blue-green.sh and
# docs/deployment/vps-guide.md for the full runbook.

deploy-bg:
	./scripts/deploy-blue-green.sh

deploy-bg-force:
	./scripts/deploy-blue-green.sh --force

rollback-bg:
	./scripts/deploy-blue-green.sh --rollback

logs:
	docker compose logs -f --tail=100 app frontend

logs-app:
	docker compose logs -f --tail=100 app

logs-frontend:
	docker compose logs -f --tail=100 frontend

clean:
	docker compose down -v --remove-orphans 2>/dev/null || true
	find . -type d -name __pycache__ -exec rm -rf {} + 2>/dev/null || true
	find . -type d -name .pytest_cache -exec rm -rf {} + 2>/dev/null || true
	find . -type d -name .ruff_cache -exec rm -rf {} + 2>/dev/null || true
	find . -type d -name "*.egg-info" -exec rm -rf {} + 2>/dev/null || true
	find . -type d -name node_modules -exec rm -rf {} + 2>/dev/null || true
	find . -type d -name .svelte-kit -exec rm -rf {} + 2>/dev/null || true

# ── Backups ──────────────────────────────────────────────
# Convenience wrappers around scripts/{backup,restore}-postgres.sh.
# Requires /etc/default/doe-backup (or equivalent env) for
# S3_ENDPOINT_URL, S3_BUCKET, AWS_PROFILE. See scripts/README.md.

backup-db-dry-run:
	REPO_DIR=$(CURDIR) ./scripts/backup-postgres.sh --dry-run

backup-db:
	REPO_DIR=$(CURDIR) ./scripts/backup-postgres.sh

restore-db-list:
	REPO_DIR=$(CURDIR) ./scripts/restore-postgres.sh --list
