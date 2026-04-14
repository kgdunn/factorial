# System Architecture

Cross-repo system architecture for the Agentic Experimental Design & Analysis platform.
For frontend-specific conventions, see the root `CLAUDE.md`. For UI/UX spec, see `frontend-spec.md`.

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

## Monorepo Decision

This project uses a monorepo (`backend/` + `frontend/`) rather than separate repositories.

### Why monorepo over separate repos

- **Single docker-compose** deploys both services. One `git pull && docker compose up --build` on the Hetzner VPS.
- **One git clone for full context** — AI agents (and humans) see the entire system without cross-repo coordination. No need to tell the agent "look here for the backend, look there for the frontend."
- **API contract co-evolution** — when a backend response schema changes, the frontend fetch call updates in the same PR. No version coordination dance.
- **The project is small-team/solo** — separate repos add CI/versioning/deploy overhead without the team-boundary benefits that justify them at scale.

### Why the frontend and backend are still decoupled

- They communicate over HTTP (`/api/v1/`). No shared code or imports.
- Each has its own Dockerfile, package manager (uv vs npm), and CI workflow with path filters.
- Putting them in the same repo doesn't couple the code — it just simplifies the workflow.

### Deployment simplicity

- Target is a single **Hetzner VPS** running docker-compose.
- Graduation path to separate services (container orchestration, CDN for static assets) doesn't require repo separation — just separate Dockerfiles (which we already have).

## Tech Stack

| Layer | Technology | Purpose |
|-------|------------|---------|
| Frontend | SvelteKit + Svelte 5 | UI framework |
| Styling | Tailwind CSS 4 | Utility-first CSS |
| Visualization | ECharts + echarts-gl | Interactive charts, 3D surfaces |
| API | FastAPI + Uvicorn | Async Python API |
| ORM | SQLAlchemy 2.0 async | PostgreSQL access |
| Migrations | Alembic | Schema versioning |
| Relational DB | PostgreSQL 16 | Experiments, users, results |
| Knowledge Graph | Neo4j 5 Community | Entity relationships, domain ontology |
| Agent LLM | Anthropic API (Claude) | Conversational agent |
| Agent Orchestration | LangGraph (planned) | Multi-step workflows |
| Observability | LangSmith or Langfuse (planned) | Agent tracing |
| Config | pydantic-settings | Environment-based config |
| Backend Packages | UV | Python dependency management |
| Frontend Packages | npm | Node dependency management |
| Containers | Docker + docker-compose | Deployment |
| CI/CD | GitHub Actions | Automated testing/builds |

## Agent Tools (planned)

The agent will have access to these tools via LangGraph tool nodes, calling the `process-improve` package:

### 1. create_design
Generate an experimental design matrix.
- **Input**: factors (names, levels, types), design type (full factorial, fractional, CCD, BBD, optimal, mixture, screening), optional constraints
- **Output**: design matrix (runs x factors), design properties (resolution, aliasing)

### 2. analyze_results
Fit a model to experimental results.
- **Input**: design matrix, response values (partial OK), model type (linear, interaction, quadratic)
- **Output**: coefficients, p-values, R², adjusted R², ANOVA table, residuals

### 3. create_visualization
Generate interactive chart data for ECharts.
- **Input**: visualization type (response_surface, contour, main_effects, interaction, pareto, normal_probability, residual), model reference, axis factors
- **Output**: ECharts option object (ready for frontend rendering)

### 4. suggest_next_runs
Recommend additional experimental runs.
- **Input**: current design + results, objective (reduce variance, explore region, validate model)
- **Output**: recommended runs with rationale

### 5. validate_design
Check a proposed design for issues.
- **Input**: design matrix, factors
- **Output**: warnings (confounding, low power, missing interactions), suggestions

### 6. compare_designs
Compare multiple design alternatives.
- **Input**: list of designs
- **Output**: comparison table (runs, resolution, D-efficiency, power)

### 7. run_pca / run_pls
Multivariate analysis tools.
- **Input**: data matrix, number of components
- **Output**: scores, loadings, explained variance, diagnostics

### 8. control_chart
Statistical process control.
- **Input**: process data, chart type (Shewhart, CUSUM, EWMA)
- **Output**: chart data with control limits, out-of-control signals

## Neo4j Knowledge Graph Schema (planned)

```
(:User)-[:OWNS]->(:Experiment)-[:HAS_FACTOR]->(:Factor)
(:Experiment)-[:HAS_RESPONSE]->(:Response)
(:Experiment)-[:USED_DESIGN]->(:Design)
(:Experiment)-[:PRODUCED]->(:Model)-[:HAS_VISUALIZATION]->(:Visualization)
(:Model)-[:SHARED_AS]->(:PublicModel)
(:User)-[:HAS_ROLE]->(:Role)
(:Experiment)-[:IN_DOMAIN]->(:Domain)
```

## Docker Compose Services

| Service | Image | Port | Purpose |
|---------|-------|------|---------|
| app | Custom (backend/Dockerfile) | 8000 | FastAPI backend |
| frontend | Custom (frontend/Dockerfile) | 3000 (→80) | SvelteKit via nginx |
| postgres | postgres:16-alpine | 5432 | Relational storage |
| neo4j | neo4j:5-community | 7474, 7687 | Knowledge graph |
| redis | redis:7-alpine (deferred) | 6379 | Sessions/caching |

## Deployment Target

**Hetzner VPS** running docker-compose. Single server for MVP.

Graduation path:
- Phase 1 (MVP): Single VPS with docker-compose
- Phase 2: Managed PostgreSQL, static assets via CDN
- Phase 3: Container orchestration, managed Neo4j
