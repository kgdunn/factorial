"""Unit tests for ``app.services.balance_service``."""

from __future__ import annotations

import uuid
from decimal import Decimal

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.admin_event import AdminEvent
from app.models.user import User
from app.models.user_balance import UserBalance
from app.services import balance_service


async def _make_user(db: AsyncSession) -> User:
    user = User(
        email=f"u{uuid.uuid4().hex[:8]}@example.com",
        password_hash="x",  # noqa: S106 — not a real password; test fixture only
    )
    db.add(user)
    await db.flush()
    return user


async def test_ensure_balance_creates_zero_row(db_session: AsyncSession) -> None:
    user = await _make_user(db_session)
    balance = await balance_service.ensure_balance(db_session, user.id)
    assert balance.balance_usd == Decimal("0")
    assert balance.balance_tokens == 0


async def test_top_up_adds_and_logs_event(db_session: AsyncSession) -> None:
    user = await _make_user(db_session)

    balance = await balance_service.top_up(
        db_session,
        user_id=user.id,
        usd=Decimal("25.5000"),
        tokens=1_000_000,
        actor_email="admin@example.com",
    )
    assert balance.balance_usd == Decimal("25.5000")
    assert balance.balance_tokens == 1_000_000

    balance = await balance_service.top_up(
        db_session,
        user_id=user.id,
        usd=Decimal("0"),
        tokens=500_000,
        actor_email="admin@example.com",
    )
    assert balance.balance_usd == Decimal("25.5000")
    assert balance.balance_tokens == 1_500_000

    stored = (await db_session.execute(select(UserBalance).where(UserBalance.user_id == user.id))).scalar_one()
    assert stored.balance_tokens == 1_500_000

    events = (
        (await db_session.execute(select(AdminEvent).where(AdminEvent.event_type == "balance_topup"))).scalars().all()
    )
    assert len(events) == 2
    assert events[0].status == "info"
    assert events[0].payload["user_id"] == str(user.id)
