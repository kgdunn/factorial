# Linting & Formatting

## Check for Issues

```bash
make lint
```

This runs `ruff check` and `ruff format --check` on the backend code. Read-only — no files are modified.

## Auto-fix and Format

```bash
make format
```

This runs `ruff check --fix` and `ruff format` to automatically fix lint issues and format code.

## Configuration

- **Tool**: [ruff](https://docs.astral.sh/ruff/)
- **Line length**: 120 characters
- **Rules**: E, W, F, I, N, UP, B, S, T20, SIM
- **Imports**: sorted by ruff (isort-compatible), `app` is first-party

Configuration lives in `backend/pyproject.toml` under `[tool.ruff]`.
