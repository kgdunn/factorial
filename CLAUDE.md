# CLAUDE.md — Agent Context

## Project Overview

**Agentic Experimental Design & Analysis** is a monorepo containing the backend API (FastAPI) and frontend (SvelteKit) for an AI agent-based web application that helps users design, run, and analyze scientific experiments using Design of Experiments (DOE) methodology.

The actual statistical analysis tools live in a **separate package**: [`process-improve`](https://github.com/kgdunn/process-improve). That package provides PCA, PLS, factorial designs, response surface methodology, control charts, and more. The backend calls those tools via LangGraph agent orchestration (not yet implemented).

For full system architecture (agent tools, knowledge graph schema, deployment), see `docs/architecture.md`.
For frontend UI/UX spec (pages, components, streaming protocol), see `docs/frontend-spec.md`.

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
| Deployment target | Hetzner VPS with docker-compose |

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
├── docs/                   # Architecture and specs
│   ├── architecture.md     # System architecture + monorepo rationale
│   └── frontend-spec.md    # Frontend UI/UX specification
├── docker-compose.yml      # Full-stack orchestration
├── Makefile                # Unified build targets
├── .env.example            # Environment template
├── .github/workflows/      # CI pipelines
├── CLAUDE.md
├── README.md
└── LICENSE
```

## Development Conventions

### Backend (Python)

- **Python >= 3.12** — use modern syntax (type unions with `|`, etc.)
- **Line length**: 120 characters
- **Linting**: ruff with rules E, W, F, I, N, UP, B, S, T20, SIM
- **Pre-commit check**: before committing, always run **both** `ruff check src/ tests/` **and** `ruff format --check src/ tests/` from `backend/`. CI runs both and will fail if either reports issues. Use `ruff format src/ tests/` to auto-fix formatting.
- **Versioning**: bump the patch (last) number in `version` in `backend/pyproject.toml` with each PR (e.g. `"0.2.0"` → `"0.2.1"`).
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
| `make deploy` | Build and start all Docker services (backend + frontend + databases) |
| `make clean` | Tear down Docker services, remove caches (Python + Node) |
| `make lint` | Check backend code with ruff (no modifications) |
| `make format` | Auto-fix backend lint issues and format code |
| `make test` | Run backend pytest |
| `make migrate` | Run Alembic migrations (upgrade to head) |
| `make frontend-install` | Install frontend npm dependencies |
| `make frontend-dev` | Start SvelteKit dev server (port 5173) |
| `make frontend-build` | Build frontend for production |

## Future Architecture (not yet implemented)

### Agent Orchestration
- **LangGraph** for multi-step agent workflows (design experiment -> analyze -> present)
- **Raw Anthropic SDK** for LLM API calls within LangGraph nodes
- **LangSmith or Langfuse** for agent observability/tracing

### Streaming
- **SSE (Server-Sent Events)** via FastAPI's `EventSourceResponse` for streaming agent responses
- POST + SSE pattern: user sends message via POST, agent streams back via SSE
- Cancel via `AbortController` on client or POST to `/cancel`

### Authentication
- **JWT auth** with `python-jose` + `passlib` + `OAuth2PasswordBearer` for MVP
- Graduate to AWS Cognito or Supabase Auth when social login/MFA needed

### DOE Tools (from process-improve package)
- Factorial designs (full/fractional)
- Response surface methodology
- Optimal designs, mixture designs, screening designs
- PCA, PLS for multivariate analysis
- Control charts (Shewhart, CUSUM, EWMA)
- The agent will call these tools via LangGraph tool nodes

### Redis
- Deferred for now (commented out in docker-compose.yml)
- Will be added for session state, agent conversation caching, JWT token management
