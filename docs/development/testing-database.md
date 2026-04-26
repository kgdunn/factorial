# Testing database

## Why real Postgres

The backend test suite used to run against in-memory SQLite via `aiosqlite`.
That kept the suite hermetic and fast, but it produced a recurring class of
bug: tests passed locally and in CI, then failed in production on Postgres.

Concrete divergences we hit in the SQLite era:

- **JSONB rendering.** `AdminEvent.payload` and `ChatEvent.data` are JSONB
  in production. SQLite has no JSONB, so the models declared
  `JSON().with_variant(JSONB(), "postgresql")` and the JSONB-specific
  behaviour — operators (`@>`, `->>`), GIN indexes, jsonb_path queries,
  NULL semantics — was never exercised in tests.
- **`gen_random_uuid()` server defaults.** Postgres has the function
  natively; SQLite does not. Every per-file fixture monkey-patched
  `Base.metadata` to swap the server default for a Python `uuid.uuid4`
  callable. Tests therefore never exercised the actual default-value
  path that production rows take.
- **`INET` columns.** `User.last_login_ip` and `Session.ip` use the
  Postgres `INET` type; SQLite saw `String(45)`. INET-specific casts
  and constraints were untested.
- **Schema source.** Tests called `Base.metadata.create_all()` to build
  the schema. Alembic migrations were therefore never executed by the
  test suite — drift between the ORM and the migrations only surfaced
  at deploy time.

## What we run instead

A dedicated Postgres 16 container, on port 5433 locally (`postgres-test`
in `docker-compose.yml`) and via `services: postgres` in CI. The schema
is built once per pytest session by running `alembic upgrade head`
in-process, and each test runs inside an outer transaction that is
rolled back at teardown so the database is fully isolated between tests
with sub-second per-test overhead.

The relevant pieces:

- `docker-compose.yml` — `postgres-test` service, named volume
  `postgres_test_data`. Brought up explicitly with
  `docker compose up -d postgres-test`. Survives reboots.
- `backend/src/app/config.py` — `postgres_test_*` fields and
  `database_url_test` / `database_url_test_sync` properties.
- `backend/alembic/env.py` — prefers `config.get_main_option("sqlalchemy.url")`
  if set, so the conftest can point Alembic at the test DB without
  touching `settings`. Plain `make migrate` and `alembic upgrade head`
  continue to use `database_url_sync`.
- `backend/tests/conftest.py` — three database-related fixtures:
    - `_test_engine` (session scope): drops + recreates the `public`
      schema for a clean slate, runs `alembic upgrade head`, yields an
      async engine.
    - `db_session`: opens a connection, begins an outer transaction,
      yields an `AsyncSession` bound to it with
      `join_transaction_mode="create_savepoint"`. Test code (and route
      handlers via `Depends(get_db_session)`) can call
      `session.commit()` freely — each commit becomes a SAVEPOINT
      release inside the rolled-back outer transaction.
    - `db_session_factory`: same plumbing, but yields an
      `async_sessionmaker` for tests that patch a module-level
      `async_session_factory` (e.g. background services that open
      their own session).

The auth overrides (`require_auth`, `require_api_key`, `require_csrf`)
remain in `conftest.py` and continue to short-circuit authentication
during tests.

## Schema source: Alembic migrations vs. `create_all()`

This decision drove the bulk of the design. Both options are viable;
we chose Alembic, but the trade-off is real and worth recording.

### Option A — `alembic upgrade head` (chosen)

Run the real migration chain against the test DB at session start.

- **Pros**
    - Tests exercise the same schema-build path production uses. Any
      drift between the ORM and the migrations becomes a CI failure
      instead of a deploy-time surprise.
    - Broken migrations fail the test suite immediately. With
      blue-green deploys we can no longer afford to discover a bad
      migration on production. Catching it in CI is the whole point.
    - No special-casing in fixture code. The fixture sets
      `sqlalchemy.url` on the Alembic config and calls
      `command.upgrade`; no model walking, no default monkey-patching,
      no schema drift workarounds.
- **Cons**
    - Adds ~1–2 s to test-session startup. Negligible against a multi-
      minute suite, invisible after the first iteration of a TDD loop.
    - A malformed Alembic revision now breaks the entire suite. This is
      arguably a feature, but it does mean the suite fails noisier
      during migration authoring. The fix is the same as it always
      was: write a working migration.
    - Slightly more involved fixture: the conftest has to drop and
      recreate the `public` schema before the upgrade so reruns start
      from a clean slate. (Alembic's `downgrade base` would also work
      but is slower and depends on every migration being reversible,
      which is not a discipline we want to add right now.)

### Option B — `Base.metadata.create_all()` (rejected)

Build the schema directly from the SQLAlchemy models, same as the old
SQLite fixtures.

- **Pros**
    - Marginally faster session startup.
    - Slightly simpler fixture — no Alembic plumbing.
- **Cons**
    - Migrations remain untested. ORM ↔ migration drift stays invisible
      until a deploy. This is one of the bigger silent-divergence
      classes we set out to fix.
    - With blue-green deploys (see
      [VPS deployment guide](../deployment/vps-guide.md)), shipping a
      broken migration is a user-visible outage. Catching it in CI is
      cheap insurance.

### Switching modes

The choice lives entirely inside `conftest.py`. Replace the
`_alembic_upgrade_head()` call in the `_test_engine` fixture with
`Base.metadata.create_all()` (and drop the schema-reset block) to flip
back to the cheaper mode. Don't ship that without a follow-up plan to
test migrations elsewhere.

## Local workflow

```bash
docker compose up -d postgres-test    # one-time per machine
make test                              # full suite
```

`make test` preflights `pg_isready` and prints the missing-container
hint if the DB is unreachable.

## CI workflow

`.github/workflows/ci-backend.yml` defines the `test` job. The
`services: postgres` stanza spins up `postgres:16-alpine` for the job's
lifetime; the conftest connects to it on `localhost:5432` (CI binds
5432:5432 since nothing else is competing for the port).

## Future: parallel runs with `pytest-xdist`

Not currently used. If you add it, the conftest needs:

- A per-worker database name (suffix `PYTEST_XDIST_WORKER` onto
  `database_url_test`), or
- A template-DB clone: run migrations against a template DB once at
  session start, then `CREATE DATABASE worker_<n> WITH TEMPLATE
  doe_test_db_template` for each worker. Cheap because Postgres copies
  files, not data.

Either way, the existing per-test transaction-rollback fixture stays
the same.
