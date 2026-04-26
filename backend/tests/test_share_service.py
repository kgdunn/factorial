"""Unit tests for ``app.services.share_service``.

Covers token uniqueness, revoke behaviour, expiry handling, and the
atomic ``view_count`` increment in ``resolve_public_share``. Uses the
session-scoped Postgres ``db_session`` fixture from ``conftest.py``.
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime, timedelta

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.experiment import Experiment
from app.models.experiment_share import ExperimentShare
from app.models.user import User
from app.services import share_service


async def _make_user(session: AsyncSession, user_id: uuid.UUID) -> User:
    user = User(
        id=user_id,
        email=f"u-{user_id.hex[:8]}@example.com",
        password_hash="x",  # noqa: S106 — fixture-only
    )
    session.add(user)
    await session.flush()
    return user


async def _make_experiment(session: AsyncSession, owner_id: uuid.UUID) -> Experiment:
    await _make_user(session, owner_id)
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
        expires_at=None,
        never_expire=False,
        allow_results=True,
    )
    s2 = await share_service.create_share(
        db_session,
        exp.id,
        user_id=owner,
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
        expires_at=None,
        never_expire=True,
        allow_results=True,
    )
    assert share is not None

    ok = await share_service.revoke_share(db_session, share.token, user_id=owner)
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
        expires_at=None,
        never_expire=True,
        allow_results=True,
    )
    assert share is not None
    await share_service.revoke_share(db_session, share.token, user_id=owner)
    assert await share_service.resolve_public_share(db_session, share.token) is None


@pytest.mark.asyncio
async def test_resolve_public_share_rejects_expired(db_session: AsyncSession):
    owner = uuid.uuid4()
    exp = await _make_experiment(db_session, owner_id=owner)
    share = await share_service.create_share(
        db_session,
        exp.id,
        user_id=owner,
        expires_at=datetime.now(UTC) - timedelta(seconds=1),
        never_expire=False,
        allow_results=True,
    )
    assert share is not None
    assert await share_service.resolve_public_share(db_session, share.token) is None


@pytest.mark.asyncio
async def test_resolve_public_share_unknown_token(db_session: AsyncSession):
    assert await share_service.resolve_public_share(db_session, "does-not-exist") is None
