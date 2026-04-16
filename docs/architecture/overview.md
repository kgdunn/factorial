# System Architecture

Cross-repo system architecture for the Agentic Experimental Design & Analysis platform.

## Product Overview

An AI agent-based web application that helps users design, run, and analyze scientific experiments using Design of Experiments (DOE) methodology. The agent (powered by the Anthropic API) is the primary mode of interaction — it challenges user designs, advises on alternatives, and guides analysis.

### Key Features

- **User signup** with role/background selection
- **Agent-first chat UI** as the primary interaction mode
- **Experiment design** via conversational agent (factorial, RSM, optimal, mixture, screening)
- **Incremental results entry** — users enter results as they become available
- **Partial and full analysis** of experimental results
- **Interactive visualization** — the main differentiator (3D response surfaces, contour plots, interaction plots)
- **Model save/share** — save models and share publicly

## Architecture Diagram

```
┌─────────────────────────────────────────────────────┐
│                  FastAPI + Uvicorn                  │
│  ┌───────────┐  ┌───────────┐  ┌────────────────┐   │
│  │ /api/v1/  │  │ Pydantic  │  │   Middleware   │   │
│  │ endpoints │  │ schemas   │  │ (CORS, etc.)   │   │
│  └─────┬─────┘  └───────────┘  └────────────────┘   │
│        │                                            │
│  ┌─────▼──────────────┐  ┌────────────────────────┐ │
│  │ SQLAlchemy async   │  │ Neo4j async driver     │ │
│  │ (get_db_session)   │  │ (get_neo4j_session)    │ │
│  └─────┬──────────────┘  └──────┬─────────────────┘ │
└────────┼────────────────────────┼───────────────────┘
         │                        │
    ┌────▼─────┐            ┌─────▼─────┐
    │ Postgres │            │   Neo4j   │
    │    16    │            │ Community │
    └──────────┘            └───────────┘

┌─────────────────────────────────────────────────────┐
│             SvelteKit (Static Adapter)              │
│  ┌───────────┐  ┌───────────┐  ┌────────────────┐   │
│  │ Routes    │  │ Components│  │ Stores         │   │
│  │ (pages)   │  │ (Svelte5) │  │ (state mgmt)   │   │
│  └───────────┘  └───────────┘  └────────────────┘   │
│                     │                               │
│              fetch /api/v1/*                        │
└─────────────────────┼───────────────────────────────┘
                      │ HTTP
                      ▼
              FastAPI backend
```

## Health Endpoints

- `GET /api/v1/health` — Liveness probe (is the API process running?)
- `GET /api/v1/health/ready` — Readiness probe (are PostgreSQL and Neo4j connected?)

## Docker Compose Services

| Service | Image | Port | Purpose |
|---------|-------|------|---------|
| app | Custom (backend/Dockerfile) | 8000 | FastAPI backend |
| frontend | Custom (frontend/Dockerfile) | 3000 (→80) | SvelteKit via nginx |
| postgres | postgres:16-alpine | 5432 | Relational storage |
| neo4j | neo4j:5-community | 7474, 7687 | Knowledge graph |
| redis | redis:7-alpine (deferred) | 6379 | Sessions/caching |

## Deployment Target

**Linux VPS** running docker-compose. Single server for MVP.

Graduation path:

- Phase 1 (MVP): Single VPS with docker-compose
- Phase 2: Managed PostgreSQL, static assets via CDN
- Phase 3: Container orchestration, managed Neo4j
