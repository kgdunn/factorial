"""Per-user balance service (prepaid dollars + tokens).

Balances are stored in the ``user_balances`` table. Admins top them up
via the admin panel; every top-up is audited through an ``admin_event``
row (``event_type='balance_topup'``, ``status='info'``).

Consumption (deducting spend as conversations run) is not wired in yet;
that's a follow-up once product decides on enforcement semantics.
"""

from __future__ import annotations

import uuid
from decimal import Decimal

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.user_balance import UserBalance
from app.services import admin_event_service


async def get_balance(db: AsyncSession, user_id: uuid.UUID) -> UserBalance | None:
    """Return the balance row for a user, or ``None`` if none exists."""
    result = await db.execute(select(UserBalance).where(UserBalance.user_id == user_id))
    return result.scalar_one_or_none()


async def ensure_balance(db: AsyncSession, user_id: uuid.UUID) -> UserBalance:
    """Return the balance row, creating a zero one if missing."""
    balance = await get_balance(db, user_id)
    if balance is not None:
        return balance
    balance = UserBalance(user_id=user_id, balance_usd=Decimal("0"), balance_tokens=0)
    db.add(balance)
    await db.flush()
    return balance


async def top_up(
    db: AsyncSession,
    *,
    user_id: uuid.UUID,
    usd: Decimal,
    tokens: int,
    actor_email: str | None,
) -> UserBalance:
    """Add ``usd`` and ``tokens`` to a user's balance and log an admin event.

    Either amount may be zero, but at least one must be positive — callers
    should validate that before calling.
    """
    balance = await ensure_balance(db, user_id)
    balance.balance_usd = (balance.balance_usd or Decimal("0")) + usd
    balance.balance_tokens = (balance.balance_tokens or 0) + tokens
    await db.flush()

    await admin_event_service.log_snapshot(
        db,
        event_type="balance_topup",
        source="admin_api",
        payload={
            "user_id": str(user_id),
            "usd": str(usd),
            "tokens": tokens,
            "new_balance_usd": str(balance.balance_usd),
            "new_balance_tokens": balance.balance_tokens,
        },
        message=f"Top-up by {actor_email or 'unknown'}: +${usd} / +{tokens} tokens",
    )
    return balance
