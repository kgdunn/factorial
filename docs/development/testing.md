# Testing

## Running Tests

```bash
make test
```

Tests run with `APP_ENV=testing`, which skips database connectivity checks. No running PostgreSQL or Neo4j required for unit tests.

## Test Frameworks

- **Backend**: pytest + pytest-asyncio
- **Frontend**: vitest for unit tests, Playwright for E2E (when added)
