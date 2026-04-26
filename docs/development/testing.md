# Testing

## Running Tests

```bash
docker compose up -d postgres-test   # one-time per machine
make test
```

The backend test suite runs against a real **PostgreSQL 16** instance — the
`postgres-test` service in `docker-compose.yml` (port 5433, database
`doe_test_db`). The dev Postgres on 5432 is left untouched, so test runs
cannot stomp on dev data. CI provisions an equivalent service via
`services: postgres` on the `test` job in `.github/workflows/ci-backend.yml`.

If `pg_isready` cannot reach the test database, `make test` exits with a
one-line hint pointing at the `docker compose up -d postgres-test` command.

## Test Frameworks

- **Backend**: pytest + pytest-asyncio (`asyncio_mode = "auto"`)
- **Frontend**: vitest for unit tests, Playwright for E2E (when added)

## Backend test database

For the design rationale (why real Postgres instead of SQLite, how the
fixtures are wired, what `pytest-xdist` would need) see
[Testing database](testing-database.md).
