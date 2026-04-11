# CLAUDE.md — Agent Context

## Project Overview

**Agentic Experimental Design & Analysis** is the backend API for an AI agent-based web application that helps users design, run, and analyze scientific experiments using Design of Experiments (DOE) methodology.

This repo contains **only the backend** (FastAPI). The frontend (SvelteKit) will be a separate concern.

The actual statistical analysis tools live in a **separate package**: [`process-improve`](https://github.com/kgdunn/process-improve). That package provides PCA, PLS, factorial designs, response surface methodology, control charts, and more. This backend will call those tools via LangGraph agent orchestration (not yet implemented).

## Tech Stack

| Layer | Technology |
|-------|------------|
| API framework | FastAPI + Uvicorn (ASGI) |
| ORM | SQLAlchemy 2.0 async |
| Migrations | Alembic |
| Primary database | PostgreSQL 16 |
| Knowledge graph | Neo4j 5 Community Edition |
| Config management | pydantic-settings (reads .env) |
| Package manager | UV |
| Linting/formatting | ruff |
| Testing | pytest + pytest-asyncio + httpx |
| Containerization | Docker + docker-compose |
| CI/CD | GitHub Actions |

## Project Structure

```
src/app/              # Main application package
├── main.py           # FastAPI app, lifespan, middleware, router mounting
├── config.py         # Settings class (pydantic-settings, reads .env)
├── api/v1/           # Versioned API routes
│   ├── router.py     # v1 router aggregator
│   └── endpoints/    # Individual endpoint modules
├── db/               # PostgreSQL layer
│   ├── session.py    # async engine + session factory + get_db_session dependency
│   └── base.py       # SQLAlchemy DeclarativeBase
├── graph/            # Neo4j layer
│   └── neo4j_driver.py  # async driver + get_neo4j_session dependency
├── models/           # SQLAlchemy ORM models (future)
└── schemas/          # Pydantic request/response schemas
```

## Development Conventions

### Code Style
- **Python >= 3.12** — use modern syntax (type unions with `|`, etc.)
- **Line length**: 120 characters
- **Linting**: ruff with rules E, W, F, I, N, UP, B, S, T20, SIM
- **Imports**: sorted by ruff (isort-compatible), `app` is first-party
- **Async-first**: all database operations use async drivers (asyncpg for PostgreSQL, neo4j async for Neo4j)

### Architecture Patterns
- **src layout**: code lives in `src/app/`, imported as `from app.xxx import yyy`
- **Versioned API**: all routes under `/api/v1/` prefix, new versions get `/api/v2/` etc.
- **Dependency injection**: use FastAPI's `Depends()` for database sessions, Neo4j sessions, auth, etc.
- **Lifespan pattern**: startup/shutdown logic in `main.py` async context manager (not deprecated `on_event`)
- **Settings via environment**: `pydantic-settings` reads from `.env` file and env vars. Never hardcode credentials.
- **DB sessions**: `get_db_session()` yields an `AsyncSession`, auto-commits on success, rolls back on exception

### Database
- PostgreSQL for structured/relational data (experiments, users, results)
- Neo4j for knowledge graph (entity relationships, domain ontology, RAG)
- Alembic for PostgreSQL schema migrations (runs synchronously with psycopg2)
- All SQLAlchemy models inherit from `app.db.base.Base`

### Testing
- Set `APP_ENV=testing` to skip database connectivity checks in lifespan
- Use `httpx.AsyncClient` with `ASGITransport` for async endpoint tests
- Tests do NOT require running PostgreSQL or Neo4j (mocked/skipped in test mode)
- Run with: `make test`

## Make Targets

| Command | What it does |
|---------|-------------|
| `make install` | Install all dependencies (main + dev) via UV |
| `make debug` | Start uvicorn with hot-reload on port 8000 |
| `make deploy` | Build and start all Docker services (app + postgres + neo4j) |
| `make clean` | Tear down Docker services, remove caches |
| `make lint` | Check code with ruff (no modifications) |
| `make format` | Auto-fix lint issues and format code |
| `make test` | Run pytest |
| `make migrate` | Run Alembic migrations (upgrade to head) |

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

### Infrastructure Graduation Path
- Phase 1 (MVP): Single EC2 t4g with docker-compose (~$25/month)
- Phase 2: PostgreSQL -> RDS, frontend -> S3 + CloudFront (~$60-80/month)
- Phase 3: Backend -> ECS Fargate, Neo4j -> AuraDB (~$150/month)

### Redis
- Deferred for now (commented out in docker-compose.yml)
- Will be added for session state, agent conversation caching, JWT token management
