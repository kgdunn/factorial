# Monorepo Rationale

This project uses a monorepo (`backend/` + `frontend/`) rather than separate repositories.

## Why monorepo over separate repos

- **Single docker-compose** deploys both services. One `git pull && docker compose up --build` on the VPS.
- **One git clone for full context** — coding agents (and humans) see the entire system without cross-repo coordination. No need to tell the agent "look here for the backend, look there for the frontend."
- **API contract co-evolution** — when a backend response schema changes, the frontend fetch call updates in the same PR. No version coordination dance.
- **The project is small-team/solo** — separate repos add CI/versioning/deploy overhead without the team-boundary benefits that justify them at scale.

## Why the frontend and backend are still decoupled

- They communicate over HTTP (`/api/v1/`). No shared code or imports.
- Each has its own Dockerfile, package manager (uv vs npm), and CI workflow with path filters.
- Putting them in the same repo doesn't couple the code — it just simplifies the workflow.

## Deployment simplicity

- Target is a single **Linux VPS** running docker-compose.
- Graduation path to separate services (container orchestration, CDN for static assets) doesn't require repo separation — just separate Dockerfiles (which we already have).
