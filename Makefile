.PHONY: install debug deploy deploy-preflight deploy-up deploy-migrate \
       clean lint format test migrate \
       frontend-install frontend-dev frontend-build

# ── Backend ──────────────────────────────────────────────

install:
	@echo "==> Installing/updating UV..."
	curl -LsSf https://astral.sh/uv/install.sh | sh
	cd backend && uv sync --all-extras

debug:
	cd backend && uv run uvicorn app.main:app --reload --host 0.0.0.0 --port 8000

lint:
	cd backend && uv run ruff check src/ tests/
	cd backend && uv run ruff format --check src/ tests/

format:
	cd backend && uv run ruff check --fix src/ tests/
	cd backend && uv run ruff format src/ tests/

test:
	cd backend && APP_ENV=testing uv run pytest tests/ -v --tb=short

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

clean:
	docker compose down -v --remove-orphans 2>/dev/null || true
	find . -type d -name __pycache__ -exec rm -rf {} + 2>/dev/null || true
	find . -type d -name .pytest_cache -exec rm -rf {} + 2>/dev/null || true
	find . -type d -name .ruff_cache -exec rm -rf {} + 2>/dev/null || true
	find . -type d -name "*.egg-info" -exec rm -rf {} + 2>/dev/null || true
	find . -type d -name node_modules -exec rm -rf {} + 2>/dev/null || true
	find . -type d -name .svelte-kit -exec rm -rf {} + 2>/dev/null || true
