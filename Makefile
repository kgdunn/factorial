.PHONY: help install relock debug deploy deploy-preflight deploy-up deploy-migrate \
       deploy-bg deploy-bg-force rollback-bg \
       logs logs-app logs-frontend \
       timing-tail timing-slowest timing-turn timing-by-kind timing-tools-slowest \
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
	@echo "  relock             Regenerate backend + frontend lock files and refresh .venv / node_modules"
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
	@echo "Chat-turn timing (reads TIMING_LOG inside the app container; default /app/logs/timing.jsonl):"
	@echo "  timing-tail        Live tail timing.jsonl pretty-printed via jq"
	@echo "  timing-slowest     Top 10 slowest turns by total duration"
	@echo "  timing-turn TURN=<id>  All records for one turn_id"
	@echo "  timing-by-kind     Aggregate ms + count grouped by record kind"
	@echo "  timing-tools-slowest   Top 10 slowest tool calls"
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

relock:
	@echo "==> Upgrading backend lock file..."
	cd backend && uv lock --upgrade
	@echo "==> Syncing backend .venv from new lock..."
	cd backend && uv sync --all-extras
	@echo "==> Upgrading frontend lock file..."
	cd frontend && npm update
	@echo "==> Relock complete."

debug:
	cd backend && uv run uvicorn app.main:app --reload --host 0.0.0.0 --port 8000

lint:
	cd backend && uv run --extra dev ruff check src/ tests/
	cd backend && uv run --extra dev ruff format --check src/ tests/

format:
	cd backend && uv run --extra dev ruff check --fix src/ tests/
	cd backend && uv run --extra dev ruff format src/ tests/

test:
	@pg_isready -h $${POSTGRES_TEST_HOST:-localhost} -p $${POSTGRES_TEST_PORT:-5433} -q || { \
	    echo "ERROR: test Postgres is not reachable on $${POSTGRES_TEST_HOST:-localhost}:$${POSTGRES_TEST_PORT:-5433}."; \
	    echo "Start it with:  docker compose up -d postgres-test"; \
	    echo "(See docs/development/testing-database.md for the full workflow.)"; \
	    exit 1; \
	}
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

# ── Chat-turn timing (TIMING_LOG_PATH JSONL) ─────────────
# The agent loop writes one JSON Lines record per phase /
# api_call / tool / turn_total to TIMING_LOG_PATH (see
# backend/src/app/services/turn_timing.py and PR #101).
# These targets shell into the app container to query the
# file with jq. Override the path with TIMING_LOG=... if
# you've changed it in .env.

TIMING_LOG ?= /app/logs/timing.jsonl

timing-tail:
	docker compose exec app sh -c 'tail -f $(TIMING_LOG) | jq .'

timing-slowest:
	docker compose exec app jq -s 'map(select(.kind=="turn_total")) | sort_by(-.duration_ms) | .[0:10]' $(TIMING_LOG)

timing-turn:
	@test -n "$(TURN)" || { echo 'Usage: make timing-turn TURN=<turn_id>'; exit 2; }
	docker compose exec app jq -s --arg t '$(TURN)' 'map(select(.turn_id==$$t))' $(TIMING_LOG)

timing-by-kind:
	docker compose exec app jq -s 'group_by(.kind) | map({kind: .[0].kind, total_ms: (map(.duration_ms // .total_ms // 0) | add), n: length})' $(TIMING_LOG)

timing-tools-slowest:
	docker compose exec app jq -s 'map(select(.kind=="tool")) | sort_by(-.duration_ms) | .[0:10] | map({tool, duration_ms, status, agent_turn, turn_id})' $(TIMING_LOG)

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
