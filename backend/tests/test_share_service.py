"""Unit tests for ``app.services.share_service`` against an in-memory SQLite.

Covers token uniqueness, revoke behaviour, expiry handling, and the
atomic ``view_count`` increment in ``resolve_public_share``.
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime, timedelta

import pytest
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from app.db.base import Base
from app.models.experiment import Experiment  # noqa: F401 — register table
from app.models.experiment_share import ExperimentShare
from app.models.user import User  # noqa: F401 — register table
from app.services import share_service


@pytest.fixture
async def db_session():
    from sqlalchemy import ColumnDefault  # noqa: PLC0415

    engine = create_async_engine(
        "sqlite+aiosqlite:///:memory:",
        connect_args={"check_same_thread": False},
    )

    # Replace PG-side ``gen_random_uuid()`` defaults with a Python-side
    # ``uuid.uuid4`` so SQLite can fill PK columns without the extension.
    for table in Base.metadata.tables.values():
        for col in table.columns:
            if col.server_default is not None and "gen_random_uuid" in str(getattr(col.server_default, "arg", "")):
                col.server_default = None
                col.default = ColumnDefault(uuid.uuid4)

    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

    factory = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)
    async with factory() as session:
        yield session
    await engine.dispose()


async def _make_experiment(session: AsyncSession, owner_id: uuid.UUID | None = None) -> Experiment:
    exp = Experiment(
        id=uuid.uuid4(),
        name="Test",
        status="active",
        design_type="full_factorial",
        factors=[],
        design_data={"n_factors": 2, "n_runs": 4},
        results_data=[],
        user_id=owner_id,
    )
    session.add(exp)
    await session.flush()
    return exp


@pytest.mark.asyncio
async def test_create_share_generates_unique_token(db_session: AsyncSession):
    owner = uuid.uuid4()
    exp = await _make_experiment(db_session, owner_id=owner)

    s1 = await share_service.create_share(
        db_session,
        exp.id,
        user_id=owner,
        is_service_account=False,
        expires_at=None,
        never_expire=False,
        allow_results=True,
    )
    s2 = await share_service.create_share(
        db_session,
        exp.id,
        user_id=owner,
        is_service_account=False,
        expires_at=None,
        never_expire=False,
        allow_results=True,
    )
    assert s1 is not None and s2 is not None
    assert s1.token != s2.token
    assert s1.expires_at is not None  # default expiry applied


@pytest.mark.asyncio
async def test_create_share_never_expire(db_session: AsyncSession):
    owner = uuid.uuid4()
    exp = await _make_experiment(db_session, owner_id=owner)
    share = await share_service.create_share(
        db_session,
        exp.id,
        user_id=owner,
        is_service_account=False,
        expires_at=None,
        never_expire=True,
        allow_results=True,
    )
    assert share is not None
    assert share.expires_at is None


@pytest.mark.asyncio
async def test_create_share_rejects_non_owner(db_session: AsyncSession):
    owner = uuid.uuid4()
    other = uuid.uuid4()
    exp = await _make_experiment(db_session, owner_id=owner)
    share = await share_service.create_share(
        db_session,
        exp.id,
        user_id=other,
        is_service_account=False,
        expires_at=None,
        never_expire=True,
        allow_results=True,
    )
    assert share is None


@pytest.mark.asyncio
async def test_revoke_sets_revoked_at(db_session: AsyncSession):
    owner = uuid.uuid4()
    exp = await _make_experiment(db_session, owner_id=owner)
    share = await share_service.create_share(
        db_session,
        exp.id,
        user_id=owner,
        is_service_account=False,
        expires_at=None,
        never_expire=True,
        allow_results=True,
    )
    assert share is not None

    ok = await share_service.revoke_share(db_session, share.token, user_id=owner, is_service_account=False)
    assert ok is True

    refreshed = await db_session.get(ExperimentShare, share.id)
    assert refreshed is not None
    assert refreshed.revoked_at is not None


@pytest.mark.asyncio
async def test_resolve_public_share_happy_path_increments_view_count(
    db_session: AsyncSession,
):
    owner = uuid.uuid4()
    exp = await _make_experiment(db_session, owner_id=owner)
    share = await share_service.create_share(
        db_session,
        exp.id,
        user_id=owner,
        is_service_account=False,
        expires_at=None,
        never_expire=True,
        allow_results=True,
    )
    assert share is not None

    resolved = await share_service.resolve_public_share(db_session, share.token)
    assert resolved is not None
    got_share, got_exp = resolved
    assert got_exp.id == exp.id
    assert got_share.view_count == 1

    resolved2 = await share_service.resolve_public_share(db_session, share.token)
    assert resolved2 is not None
    assert resolved2[0].view_count == 2


@pytest.mark.asyncio
async def test_resolve_public_share_rejects_revoked(db_session: AsyncSession):
    owner = uuid.uuid4()
    exp = await _make_experiment(db_session, owner_id=owner)
    share = await share_service.create_share(
        db_session,
        exp.id,
        user_id=owner,
        is_service_account=False,
        expires_at=None,
        never_expire=True,
        allow_results=True,
    )
    assert share is not None
    await share_service.revoke_share(db_session, share.token, user_id=owner, is_service_account=False)
    assert await share_service.resolve_public_share(db_session, share.token) is None


@pytest.mark.asyncio
async def test_resolve_public_share_rejects_expired(db_session: AsyncSession):
    owner = uuid.uuid4()
    exp = await _make_experiment(db_session, owner_id=owner)
    share = await share_service.create_share(
        db_session,
        exp.id,
        user_id=owner,
        is_service_account=False,
        expires_at=datetime.now(UTC) - timedelta(seconds=1),
        never_expire=False,
        allow_results=True,
    )
    assert share is not None
    assert await share_service.resolve_public_share(db_session, share.token) is None


@pytest.mark.asyncio
async def test_resolve_public_share_unknown_token(db_session: AsyncSession):
    assert await share_service.resolve_public_share(db_session, "does-not-exist") is None
