.PHONY: install debug deploy clean lint format test migrate

install:
	uv sync --all-extras

debug:
	uv run uvicorn app.main:app --reload --host 0.0.0.0 --port 8000

deploy:
	docker compose up --build -d

clean:
	docker compose down -v --remove-orphans 2>/dev/null || true
	find . -type d -name __pycache__ -exec rm -rf {} + 2>/dev/null || true
	find . -type d -name .pytest_cache -exec rm -rf {} + 2>/dev/null || true
	find . -type d -name .ruff_cache -exec rm -rf {} + 2>/dev/null || true
	find . -type d -name "*.egg-info" -exec rm -rf {} + 2>/dev/null || true

lint:
	uv run ruff check src/ tests/
	uv run ruff format --check src/ tests/

format:
	uv run ruff check --fix src/ tests/
	uv run ruff format src/ tests/

test:
	APP_ENV=testing uv run pytest tests/ -v --tb=short

migrate:
	uv run alembic upgrade head
