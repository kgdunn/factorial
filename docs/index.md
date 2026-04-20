# Agentic Experimental Design & Analysis

!!! tip "Try it live"
    This project powers **[factori.al](https://factori.al)** — use it right away, or follow the guides below to self-host your own instance.

Conversational, LLM-assisted web application that helps users design, run, and analyze scientific experiments using Design of Experiments (DOE) methodology. The agent (powered by Claude) guides users through experimental design, executes statistical analyses, and presents interactive visualizations.

The statistical analysis engine lives in a separate package: [process-improve](https://github.com/kgdunn/process-improve).

## Key Features

- **Agent-first chat UI** as the primary interaction mode
- **Experiment design** via conversational agent (factorial, RSM, optimal, mixture, screening)
- **Incremental results entry** — enter results as experiments progress
- **Interactive visualization** — 3D response surfaces, contour plots, interaction plots
- **Model save & share** — save models and share publicly

## Documentation Sections

| Section | Description |
|---------|-------------|
| [Getting Started](getting-started/prerequisites.md) | Prerequisites, quick start, and make targets |
| [Architecture](architecture/overview.md) | System overview, monorepo rationale, tech stack, agent tools |
| [Frontend](frontend/specification.md) | UI/UX specification, components, streaming protocol |
| [Development](development/testing.md) | Testing, linting, database migrations |
| [Deployment](deployment/vps-guide.md) | Full VPS deployment guide |

## Project Structure

```
backend/     FastAPI API + PostgreSQL + Neo4j
frontend/    SvelteKit single-page application
docs/        Project documentation (this site)
```
