# Quick Start

## Backend

```bash
# Clone the repository
git clone https://github.com/kgdunn/agentic-doe.git
cd agentic-doe

# Copy the environment template
cp .env.example .env

# Install backend dependencies
make install

# Start the backend dev server (hot-reload on port 8000)
make debug
```

The API will be available at `http://localhost:8000`. Visit `http://localhost:8000/docs` for the interactive Swagger UI.

## Frontend

```bash
# Install frontend dependencies
make frontend-install

# Start the frontend dev server (port 5173)
make frontend-dev
```

## Full Stack (Docker)

```bash
# Start all services (backend + frontend + PostgreSQL + Neo4j)
make deploy

# Run database migrations
make migrate

# Check service health
curl http://localhost:8000/api/v1/health
curl http://localhost:3000

# Tear everything down
make clean
```
