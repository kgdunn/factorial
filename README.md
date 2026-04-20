# Agentic Experimental Design & Analysis

[![Live at factori.al](https://img.shields.io/badge/live-factori.al-blue?style=for-the-badge)](https://factori.al)
[![CI — Backend](https://github.com/kgdunn/agentic-doe/actions/workflows/ci-backend.yml/badge.svg)](https://github.com/kgdunn/agentic-doe/actions/workflows/ci-backend.yml)
[![Python 3.12+](https://img.shields.io/badge/python-3.12+-blue.svg)](https://www.python.org/downloads/)
[![FastAPI](https://img.shields.io/badge/FastAPI-0.115+-009688.svg)](https://fastapi.tiangolo.com)
[![SvelteKit](https://img.shields.io/badge/SvelteKit-2.0+-FF3E00.svg)](https://kit.svelte.dev)
[![License: Apache 2.0](https://img.shields.io/badge/license-Apache--2.0-green.svg)](LICENSE)

> **This is the open-source codebase behind [factori.al](https://factori.al)** — try it live, or clone the repo and self-host your own instance.

Conversational, LLM-assisted web application that helps users design, run, and analyze scientific experiments using Design of Experiments (DOE) methodology. The agent (powered by Claude) guides users through experimental design, executes statistical analyses, and presents interactive visualizations.

The statistical analysis engine lives in a separate package: [process-improve](https://github.com/kgdunn/process-improve).

**[Read the full documentation →](https://kgdunn.github.io/agentic-doe/)**

## Key Features

- **Agent-first chat UI** for experiment design guidance
- Support for **factorial, RSM, optimal, mixture, and screening** designs
- **Incremental results entry** as experiments progress
- **Interactive 3D response surfaces**, contour plots, and effect plots
- **Model save & share** publicly

## Quick Start

```bash
git clone https://github.com/kgdunn/agentic-doe.git
cd agentic-doe
cp .env.example .env

make install         # Backend dependencies
make debug           # Backend on :8000
make frontend-dev    # Frontend on :5173
```

See [Prerequisites](https://kgdunn.github.io/agentic-doe/getting-started/prerequisites/) and [Quick Start Guide](https://kgdunn.github.io/agentic-doe/getting-started/quickstart/) for full setup instructions including Docker.

## Project Structure

```
backend/     FastAPI API + PostgreSQL + Neo4j
frontend/    SvelteKit single-page application
docs/        Project documentation (rendered at link above)
```

## Documentation

| Topic | Link |
|-------|------|
| Prerequisites & Quick Start | [Getting Started](https://kgdunn.github.io/agentic-doe/getting-started/prerequisites/) |
| System Architecture | [Architecture](https://kgdunn.github.io/agentic-doe/architecture/overview/) |
| Frontend Specification | [Frontend](https://kgdunn.github.io/agentic-doe/frontend/specification/) |
| Development (testing, linting) | [Development](https://kgdunn.github.io/agentic-doe/development/testing/) |
| VPS Deployment Guide | [Deployment](https://kgdunn.github.io/agentic-doe/deployment/vps-guide/) |

## License

[Apache License 2.0](LICENSE) — Copyright 2026 Kevin Dunn
