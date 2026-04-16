# CLAUDE.md — Agent Context

## Project Overview

**Agentic Experimental Design & Analysis** is a monorepo containing the backend API (FastAPI) and frontend (SvelteKit) for an AI agent-based web application that helps users design, run, and analyze scientific experiments using Design of Experiments (DOE) methodology.

The actual statistical analysis tools live in a **separate package**: [`process-improve`](https://github.com/kgdunn/process-improve). That package provides PCA, PLS, factorial designs, response surface methodology, control charts, and more. The backend calls those tools via LangGraph agent orchestration (not yet implemented).

For full system architecture (agent tools, knowledge graph schema, deployment), see `docs/architecture/` (split across `overview.md`, `monorepo.md`, `tech-stack.md`, `agent-tools.md`, `knowledge-graph.md`).
For frontend UI/UX spec (pages, components, streaming protocol), see `docs/frontend/specification.md`.
For VPS deployment guide, see `docs/deployment/vps-guide.md`.
Documentation is built with MkDocs and deployed to GitHub Pages.

## Tech Stack

| Layer | Technology |
|-------|------------|
| Frontend framework | SvelteKit + Svelte 5 + Vite |
| Styling | Tailwind CSS 4 |
| Visualization | ECharts + echarts-gl |
| API framework | FastAPI + Uvicorn (ASGI) |
| ORM | SQLAlchemy 2.0 async |
| Migrations | Alembic |
| Primary database | PostgreSQL 16 |
| Knowledge graph | Neo4j 5 Community Edition |
| Config management | pydantic-settings (reads .env) |
| Backend package manager | UV |
| Frontend package manager | npm |
| Backend linting | ruff |
| Testing | pytest + pytest-asyncio (backend), vitest (frontend) |
| Containerization | Docker + docker-compose |
| CI/CD | GitHub Actions |
| Deployment target | Linux VPS with docker-compose |

## Project Structure

```
repo-root/
├── backend/                # FastAPI backend
│   ├── src/app/            # Main application package
│   │   ├── main.py         # FastAPI app, lifespan, middleware
│   │   ├── config.py       # Settings class (pydantic-settings)
│   │   ├── api/v1/         # Versioned API routes
│   │   ├── db/             # PostgreSQL layer (session, base)
│   │   ├── graph/          # Neo4j layer
│   │   ├── models/         # SQLAlchemy ORM models
│   │   ├── schemas/        # Pydantic request/response schemas
│   │   └── services/       # Business logic
│   ├── tests/              # pytest test suite
│   ├── alembic/            # Database migrations
│   ├── alembic.ini
│   ├── pyproject.toml
│   ├── uv.lock
│   ├── .python-version
│   └── Dockerfile
├── frontend/               # SvelteKit frontend
│   ├── src/
│   │   ├── app.html        # HTML shell
│   │   ├── routes/         # SvelteKit file-based routing
│   │   └── lib/            # Shared components/utilities
│   ├── static/             # Static assets
│   ├── package.json
│   ├── svelte.config.js
│   ├── vite.config.ts
│   ├── tsconfig.json
│   └── Dockerfile
├── docs/                   # MkDocs documentation source
│   ├── index.md            # Docs home page
│   ├── getting-started/    # Prerequisites, quick start, make targets
│   ├── architecture/       # Overview, monorepo, tech stack, agent tools, knowledge graph
│   ├── frontend/           # UI/UX specification
│   ├── development/        # Testing, linting, migrations
│   └── deployment/         # VPS deployment guide
├── mkdocs.yml              # MkDocs configuration
├── docker-compose.yml      # Full-stack orchestration
├── Makefile                # Unified build targets
├── .env.example            # Environment template
├── .github/workflows/      # CI pipelines (backend, frontend, docker, docs)
├── CLAUDE.md
├── README.md
└── LICENSE
```

## Versioning

The version is defined in `backend/pyproject.toml` under `[project] version`. It uses 3-part semver: `MAJOR.MINOR.PATCH` (e.g., `0.3.8`).

**Auto-bump the version with every PR that changes code or configuration:**
- **PATCH** (last position, e.g., 0.3.7 → 0.3.8): bug fixes, CI/workflow changes, docs updates, dependency bumps, small refactors, and other minor changes.
- **MINOR** (middle position, e.g., 0.3.8 → 0.4.0): new features, new modules, significant API additions, or meaningful behavioral changes. Resets PATCH to 0.
- **If unsure** whether a change is major or minor, **ask the user** before bumping.

The PyPI publish workflow (`.github/workflows/publish.yml`) automatically detects version changes on push to `main` and publishes to PyPI, then creates a GitHub Release with a `v$VERSION` tag.

## Development Conventions

### Backend (Python)

- **Python >= 3.12** — use modern syntax (type unions with `|`, etc.)
- **Line length**: 120 characters
- **Linting**: ruff with rules E, W, F, I, N, UP, B, S, T20, SIM
- **Pre-commit check**: before committing, always run **both** `ruff check src/ tests/` **and** `ruff format --check src/ tests/` from `backend/`. CI runs both and will fail if either reports issues. Use `ruff format src/ tests/` to auto-fix formatting.
- **Imports**: sorted by ruff (isort-compatible), `app` is first-party
- **Async-first**: all database operations use async drivers (asyncpg for PostgreSQL, neo4j async for Neo4j)
- **src layout**: code lives in `backend/src/app/`, imported as `from app.xxx import yyy`
- **Versioned API**: all routes under `/api/v1/` prefix, new versions get `/api/v2/` etc.
- **Dependency injection**: use FastAPI's `Depends()` for database sessions, auth, etc.
- **Lifespan pattern**: startup/shutdown logic in `main.py` async context manager (not deprecated `on_event`)
- **Settings via environment**: `pydantic-settings` reads from `.env` file and env vars. Never hardcode credentials.
- **DB sessions**: `get_db_session()` yields an `AsyncSession`, auto-commits on success, rolls back on exception

### Frontend (SvelteKit)

- **Svelte 5** with runes (`$state`, `$derived`, `$effect`) — no legacy stores API
- **TypeScript strict** for all `.ts` and `.svelte` files
- **Tailwind CSS 4** for styling — utility classes, no custom CSS unless necessary
- **ECharts** for all visualizations — no D3, no Chart.js
- **SvelteKit adapter-static** — SPA mode, served via nginx in production
- **File-based routing**: pages in `src/routes/`, layouts in `+layout.svelte`
- **API calls**: use `fetch` with `/api` prefix — proxied to backend in dev via Vite config

### Database

- PostgreSQL for structured/relational data (experiments, users, results)
- Neo4j for knowledge graph (entity relationships, domain ontology, RAG)
- Alembic for PostgreSQL schema migrations (runs from `backend/` directory)
- All SQLAlchemy models inherit from `app.db.base.Base`

### Testing

- **Backend**: Set `APP_ENV=testing` to skip database connectivity checks. Tests do NOT require running PostgreSQL or Neo4j.
- **Frontend**: vitest for unit tests, Playwright for E2E (when added)
- Run backend tests: `make test`

## Make Targets

| Command | What it does |
|---------|-------------|
| `make install` | Install backend dependencies (main + dev) via UV |
| `make debug` | Start uvicorn with hot-reload on port 8000 |
| `make deploy` | Full deploy: lint, test, build Docker images, start all services, run migrations |
| `make clean` | Tear down Docker services, remove caches (Python + Node) |
| `make lint` | Check backend code with ruff (no modifications) |
| `make format` | Auto-fix backend lint issues and format code |
| `make test` | Run backend pytest |
| `make migrate` | Run Alembic migrations (upgrade to head) |
| `make frontend-install` | Install frontend npm dependencies |
| `make frontend-dev` | Start SvelteKit dev server (port 5173) |
| `make frontend-build` | Build frontend for production |
| `make docs-serve` | Start MkDocs dev server with live reload (port 8080) |
| `make docs-build` | Build documentation site with `--strict` |

## Authentication

**Dual auth**: JWT Bearer tokens (browser users) + API key (machine-to-machine).

- **JWT**: `python-jose` + `passlib` + `bcrypt`. Short-lived access tokens (30 min) + refresh tokens (7 days).
- **API key**: `X-API-Key` header with HMAC comparison. Retained for service-to-service calls.
- **`require_auth` dependency** (`api/deps.py`): tries JWT first, falls back to API key, returns an `AuthUser` dataclass.
- **User model** (`models/user.py`): email, password_hash, display_name, background, is_active.
- **User scoping**: `user_id` FK on `conversations` and `experiments` tables. Service users see all data; regular users see only their own.
- **System prompt personalization**: user `background` field (e.g. "chemical_engineer") is appended to the agent system prompt.
- **Auth endpoints**: `POST /auth/register`, `POST /auth/login`, `POST /auth/refresh`, `GET /auth/me`.
- **Frontend**: JWT stored in localStorage, injected via `authFetch()` wrapper. Auth guard redirects to `/login`.
- **Testing bypass**: `APP_ENV=testing` returns a synthetic test user; no real auth needed in tests.

### Future auth graduation
- AWS Cognito or Supabase Auth when social login/MFA needed
- Redis for token blacklisting (currently stateless)

## Git & PR Workflow

- **Commit after every micro step** — each logical change (new file, edit, deletion) gets its own commit.
- **Push regularly** — don't accumulate unpushed commits.
- **Open a PR right away** — create a pull request as soon as the branch has its first commit. Don't wait until the work is "done."
- **Always share the PR link** — after creating a pull request, always include the PR URL in your response to the user.

## Future Architecture (not yet implemented)

### Agent Orchestration
- **LangGraph** for multi-step agent workflows (design experiment -> analyze -> present)
- Currently using raw Anthropic SDK for the agent loop
- **LangSmith or Langfuse** for agent observability/tracing

### Redis
- Deferred for now (commented out in docker-compose.yml)
- Will be added for session state, agent conversation caching, JWT token blacklisting
