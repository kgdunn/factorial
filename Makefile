.PHONY: install debug deploy clean lint format test migrate \
       frontend-install frontend-dev frontend-build

# ── Backend ──────────────────────────────────────────────

install:
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
	cd frontend && npm install

frontend-dev:
	cd frontend && npm run dev

frontend-build:
	cd frontend && npm run build

# ── Full Stack ───────────────────────────────────────────

deploy:
	docker compose up --build -d

clean:
	docker compose down -v --remove-orphans 2>/dev/null || true
	find . -type d -name __pycache__ -exec rm -rf {} + 2>/dev/null || true
	find . -type d -name .pytest_cache -exec rm -rf {} + 2>/dev/null || true
	find . -type d -name .ruff_cache -exec rm -rf {} + 2>/dev/null || true
	find . -type d -name "*.egg-info" -exec rm -rf {} + 2>/dev/null || true
	find . -type d -name node_modules -exec rm -rf {} + 2>/dev/null || true
	find . -type d -name .svelte-kit -exec rm -rf {} + 2>/dev/null || true
