# Agentic Experimental Design & Analysis

[![CI](https://github.com/kgdunn/agentic-experimental-design-and-analysis/actions/workflows/ci.yml/badge.svg)](https://github.com/kgdunn/agentic-experimental-design-and-analysis/actions/workflows/ci.yml)
[![Python 3.12+](https://img.shields.io/badge/python-3.12+-blue.svg)](https://www.python.org/downloads/)
[![FastAPI](https://img.shields.io/badge/FastAPI-0.115+-009688.svg)](https://fastapi.tiangolo.com)
[![License: BSD-3](https://img.shields.io/badge/license-BSD--3--Clause-green.svg)](LICENSE)

Backend API for an AI agent-based web application that helps users design, run, and analyze scientific experiments using Design of Experiments (DOE) methodology. The application uses LLM-powered agents to guide users through experimental design, execute statistical analyses, and present interactive visualizations of results.

The statistical analysis engine lives in a separate package: [process-improve](https://github.com/kgdunn/process-improve).

## Tech Stack

| Layer | Technology |
|-------|------------|
| API | [FastAPI](https://fastapi.tiangolo.com) + [Uvicorn](https://www.uvicorn.org) |
| Database | [PostgreSQL 16](https://www.postgresql.org) via [SQLAlchemy 2.0](https://www.sqlalchemy.org) async |
| Knowledge Graph | [Neo4j 5 Community](https://neo4j.com) |
| Migrations | [Alembic](https://alembic.sqlalchemy.org) |
| Package Manager | [UV](https://docs.astral.sh/uv/) |
| Linting | [ruff](https://docs.astral.sh/ruff/) |
| Containers | Docker + Docker Compose |
| CI/CD | GitHub Actions |

## Prerequisites

- [UV](https://docs.astral.sh/uv/getting-started/installation/) (Python package manager)
- [Docker](https://docs.docker.com/get-docker/) and [Docker Compose](https://docs.docker.com/compose/install/) (for databases and deployment)
- Python 3.12+ (UV will install this automatically)

## Quick Start

```bash
# Clone the repository
git clone https://github.com/kgdunn/agentic-experimental-design-and-analysis.git
cd agentic-experimental-design-and-analysis

# Copy the environment template
cp .env.example .env

# Install dependencies
make install

# Start the development server (hot-reload)
make debug
```

The API will be available at `http://localhost:8000`. Visit `http://localhost:8000/docs` for the interactive Swagger UI.

### With Databases (Docker)

```bash
# Start all services (FastAPI + PostgreSQL + Neo4j)
make deploy

# Run database migrations
make migrate

# Check service health
curl http://localhost:8000/api/v1/health
curl http://localhost:8000/api/v1/health/ready

# Tear everything down
make clean
```

## Make Targets

| Command | Description |
|---------|-------------|
| `make install` | Install all dependencies (main + dev) via UV |
| `make debug` | Start uvicorn with hot-reload on port 8000 |
| `make deploy` | Build and start all Docker services |
| `make clean` | Stop containers, remove volumes, clear caches |
| `make lint` | Check code with ruff (read-only) |
| `make format` | Auto-fix lint issues and format code |
| `make test` | Run test suite with pytest |
| `make migrate` | Apply database migrations with Alembic |

## Architecture

```
┌─────────────────────────────────────────────────────┐
│                    FastAPI + Uvicorn                 │
│  ┌───────────┐  ┌───────────┐  ┌────────────────┐  │
│  │ /api/v1/  │  │ Pydantic  │  │   Middleware    │  │
│  │ endpoints │  │ schemas   │  │ (CORS, etc.)   │  │
│  └─────┬─────┘  └───────────┘  └────────────────┘  │
│        │                                             │
│  ┌─────▼──────────────┐  ┌────────────────────────┐ │
│  │ SQLAlchemy async    │  │ Neo4j async driver     │ │
│  │ (get_db_session)    │  │ (get_neo4j_session)    │ │
│  └─────┬──────────────┘  └──────┬─────────────────┘ │
└────────┼────────────────────────┼───────────────────┘
         │                        │
    ┌────▼────┐             ┌─────▼─────┐
    │ Postgres │             │   Neo4j   │
    │   16     │             │ Community │
    └─────────┘             └───────────┘
```

### API Versioning

All endpoints are under `/api/v1/`. When breaking changes are needed, a `/api/v2/` prefix will be introduced alongside v1 for backwards compatibility.

### Health Endpoints

- `GET /api/v1/health` — Liveness probe (is the API process running?)
- `GET /api/v1/health/ready` — Readiness probe (are PostgreSQL and Neo4j connected?)

## Development

### Running Tests

```bash
make test
```

Tests run with `APP_ENV=testing`, which skips database connectivity checks. No running PostgreSQL or Neo4j required for unit tests.

### Linting

```bash
# Check for issues
make lint

# Auto-fix and format
make format
```

### Adding a Database Migration

```bash
# After modifying SQLAlchemy models in src/app/models/:
uv run alembic revision --autogenerate -m "description of change"

# Apply the migration:
make migrate
```

## License

[BSD 3-Clause License](LICENSE) — Copyright (c) 2026, Kevin Dunn
