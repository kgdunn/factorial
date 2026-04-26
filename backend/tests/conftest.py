"""Shared fixtures for the backend test suite.

The suite runs against a real PostgreSQL 16 instance — the
``postgres-test`` service in ``docker-compose.yml`` on port 5433
locally, or the GitHub Actions ``services: postgres`` instance in CI.
This eliminates a class of bugs where SQLite quietly accepted code
(e.g. ``JSONB`` columns, ``gen_random_uuid()`` server defaults) that
would fail in production.

Schema is built once per pytest session by running
``alembic upgrade head`` against the test DB, so ORM ↔ migration drift
fails the test suite immediately rather than at deploy time. Each test
runs inside an outer transaction that is rolled back at teardown, so
the database is fully isolated between tests with sub-second overhead.

See ``docs/development/testing-database.md`` for the design rationale and
the developer / CI workflow.
"""

import os
from collections.abc import AsyncGenerator
from pathlib import Path

import pytest
from alembic import command
from alembic.config import Config as AlembicConfig
from httpx import ASGITransport, AsyncClient
from sqlalchemy.ext.asyncio import (
    AsyncEngine,
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)

# Set testing environment before importing the app.
os.environ["APP_ENV"] = "testing"
# Run tool calls in-process during tests (no subprocess, no memory cap)
# so the suite stays fast. Production defaults to safe mode.
os.environ.setdefault("TOOL_SAFE_MODE", "false")

from app.api.csrf import require_csrf  # noqa: E402
from app.api.deps import TESTING_USER_ID, AuthUser, require_api_key, require_auth  # noqa: E402
from app.config import settings  # noqa: E402
from app.main import app  # noqa: E402

# ---------------------------------------------------------------------------
# Auth overrides for testing — replaces the old APP_ENV=testing bypass
# that lived in production code.
# ---------------------------------------------------------------------------


def _testing_user() -> AuthUser:
    """Synthetic user returned by auth dependencies during tests."""
    return AuthUser(
        id=TESTING_USER_ID,
        email="test@example.com",
        display_name="Test User",
        is_admin=True,
    )


async def _auth_override() -> AuthUser:
    return _testing_user()


async def _api_key_override() -> str:
    return "testing-bypass"


async def _csrf_override() -> None:
    """No-op CSRF check during tests — endpoints don't need a header."""
    return None


# Apply overrides so every test client skips real authentication and CSRF.
app.dependency_overrides[require_auth] = _auth_override
app.dependency_overrides[require_api_key] = _api_key_override
app.dependency_overrides[require_csrf] = _csrf_override


# ---------------------------------------------------------------------------
# Database fixtures — real Postgres, schema built via Alembic, per-test
# transaction rollback for isolation.
# ---------------------------------------------------------------------------

_ALEMBIC_INI = Path(__file__).resolve().parent.parent / "alembic.ini"


def _alembic_upgrade_head() -> None:
    """Run ``alembic upgrade head`` against the test database in-process.

    Sets ``sqlalchemy.url`` on the Alembic config so ``alembic/env.py``
    targets the test Postgres rather than the dev one, and sets
    ``script_location`` to an absolute path so the upgrade works
    regardless of the pytest CWD. Runs in the current process (no
    subprocess) so any failure surfaces as a standard Python traceback.
    """
    cfg = AlembicConfig(str(_ALEMBIC_INI))
    cfg.set_main_option("sqlalchemy.url", settings.database_url_test_sync)
    cfg.set_main_option("script_location", str(_ALEMBIC_INI.parent / "alembic"))
    command.upgrade(cfg, "head")


@pytest.fixture(scope="session")
async def _test_engine() -> AsyncGenerator[AsyncEngine, None]:
    """Session-scoped async engine with an Alembic-built schema.

    Drops and recreates the ``public`` schema before running migrations
    so reruns start from a clean slate. Cheaper than dropping the whole
    database and avoids needing CREATE DATABASE privileges.
    """
    bootstrap = create_async_engine(
        settings.database_url_test,
        isolation_level="AUTOCOMMIT",
    )
    async with bootstrap.connect() as conn:
        await conn.exec_driver_sql("DROP SCHEMA IF EXISTS public CASCADE")
        await conn.exec_driver_sql("CREATE SCHEMA public")
    await bootstrap.dispose()

    _alembic_upgrade_head()

    engine = create_async_engine(settings.database_url_test, pool_pre_ping=True)
    try:
        yield engine
    finally:
        await engine.dispose()


@pytest.fixture
async def db_session(_test_engine: AsyncEngine) -> AsyncGenerator[AsyncSession, None]:
    """Per-test ``AsyncSession`` joined to a transaction that rolls back.

    ``join_transaction_mode="create_savepoint"`` lets test code (and any
    route handler that calls ``await session.commit()`` inside the
    request) operate normally — each "commit" releases a SAVEPOINT
    inside our outer transaction rather than writing to disk. The
    explicit ``outer.rollback()`` at teardown discards everything the
    test wrote.
    """
    async with _test_engine.connect() as connection:
        outer = await connection.begin()
        try:
            session = AsyncSession(
                bind=connection,
                expire_on_commit=False,
                join_transaction_mode="create_savepoint",
            )
            try:
                yield session
            finally:
                await session.close()
        finally:
            await outer.rollback()


@pytest.fixture
async def db_session_factory(_test_engine: AsyncEngine):
    """Factory bound to a per-test connection + outer transaction.

    For tests that patch a module-level ``async_session_factory``
    (typically background services that open their own session). Every
    session produced by the factory shares the underlying connection,
    so the rollback at teardown discards everything they wrote.
    """
    async with _test_engine.connect() as connection:
        outer = await connection.begin()
        try:
            factory = async_sessionmaker(
                bind=connection,
                class_=AsyncSession,
                expire_on_commit=False,
                join_transaction_mode="create_savepoint",
            )
            yield factory
        finally:
            await outer.rollback()


# ---------------------------------------------------------------------------
# ASGI client. API tests that need a fake DB session register their own
# ``app.dependency_overrides[get_db_session]`` per-test — see
# ``test_upload_endpoints.py`` for the pattern.
# ---------------------------------------------------------------------------


@pytest.fixture
async def client():
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        yield ac
