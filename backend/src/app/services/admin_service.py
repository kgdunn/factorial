"""Admin user management: bootstrap, promote, demote, list, deactivate."""

from __future__ import annotations

import uuid
from dataclasses import dataclass, field
from datetime import datetime
from decimal import Decimal
from typing import Any

from sqlalchemy import case, func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.conversation import Conversation
from app.models.experiment import Experiment
from app.models.signup_request import SignupRequest
from app.models.user import User
from app.models.user_balance import UserBalance
from app.models.user_feedback import UserFeedback


@dataclass
class UserAggregates:
    """Per-user rollups joined onto the admin-panel user row."""

    total_cost_usd: Decimal = field(default_factory=lambda: Decimal("0"))
    total_markup_cost_usd: Decimal = field(default_factory=lambda: Decimal("0"))
    total_tokens: int = 0
    conversation_count: int = 0
    last_conversation_at: datetime | None = None
    feedback_count: int = 0
    open_experiments: int = 0
    avg_runs_per_experiment: float | None = None
    balance_usd: Decimal | None = None
    balance_tokens: int | None = None
    signup_status: str | None = None
    disclaimers_accepted: bool | None = None


async def count_admins(db: AsyncSession) -> int:
    """Count users with ``is_admin=True``."""
    result = await db.execute(select(func.count()).select_from(User).where(User.is_admin.is_(True)))
    return result.scalar_one()


async def list_admin_emails(db: AsyncSession) -> list[str]:
    """Return the emails of every active admin. Used for signup notifications."""
    result = await db.execute(select(User.email).where(User.is_admin.is_(True), User.is_active.is_(True)))
    return [email for (email,) in result.all()]


async def get_user_by_email(db: AsyncSession, email: str) -> User | None:
    """Case-sensitive email lookup (emails are stored normalized)."""
    result = await db.execute(select(User).where(User.email == email))
    return result.scalar_one_or_none()


async def create_admin_shell(db: AsyncSession, email: str, display_name: str | None = None) -> User:
    """Create an admin user with no password.

    The caller is expected to immediately issue a setup token so the admin
    can pick a password on first login.

    Raises ValueError if the email is already registered.
    """
    normalized = email.strip().lower()
    existing = await get_user_by_email(db, normalized)
    if existing is not None:
        raise ValueError(f"User {normalized} already exists")  # noqa: TRY003

    user = User(
        email=normalized,
        password_hash="",
        display_name=display_name,
        is_admin=True,
        is_active=True,
    )
    db.add(user)
    await db.flush()
    return user


async def set_admin(db: AsyncSession, user: User, is_admin: bool) -> User:
    """Toggle ``is_admin`` on a user.

    Refuses to demote the last remaining admin so the system can't lock
    itself out.
    """
    if user.is_admin and not is_admin:
        remaining = await count_admins(db)
        if remaining <= 1:
            raise ValueError("Cannot demote the last remaining admin")  # noqa: TRY003
    user.is_admin = is_admin
    await db.flush()
    return user


async def list_users(
    db: AsyncSession,
    page: int = 1,
    page_size: int = 50,
    search: str | None = None,
    admins_only: bool = False,
) -> tuple[list[User], dict[uuid.UUID, UserAggregates], int]:
    """Paginated user list for the admin UI, with per-user rollups.

    Returns ``(users, aggregates_by_id, total)``. The aggregates dict
    always contains an entry for every returned user (zero-filled if the
    user has no conversations/feedback/experiments yet).
    """
    query = select(User)
    count_query = select(func.count()).select_from(User)

    conditions: list[Any] = []
    if admins_only:
        conditions.append(User.is_admin.is_(True))
    if search:
        pattern = f"%{search.lower()}%"
        conditions.append(or_(func.lower(User.email).like(pattern), func.lower(User.display_name).like(pattern)))

    if conditions:
        query = query.where(*conditions)
        count_query = count_query.where(*conditions)

    query = query.order_by(User.created_at.desc()).offset((page - 1) * page_size).limit(page_size)
    result = await db.execute(query)
    users = list(result.scalars().all())

    total = (await db.execute(count_query)).scalar_one()

    aggregates = await _aggregate_for_users(db, users)
    return users, aggregates, total


async def _aggregate_for_users(
    db: AsyncSession,
    users: list[User],
) -> dict[uuid.UUID, UserAggregates]:
    """Batch-fetch per-user rollups for the given page of users.

    Runs five small grouped queries (one per related table) rather than
    N+1 subqueries per user. Works on both PostgreSQL (production) and
    SQLite (tests) — no dialect-specific lateral joins.
    """
    if not users:
        return {}

    ids = [u.id for u in users]
    emails_lower = [u.email.lower() for u in users]
    agg: dict[uuid.UUID, UserAggregates] = {u.id: UserAggregates() for u in users}

    conv_rows = await db.execute(
        select(
            Conversation.user_id,
            func.coalesce(func.sum(Conversation.total_cost_usd), 0),
            func.coalesce(func.sum(Conversation.total_markup_cost_usd), 0),
            func.coalesce(func.sum(Conversation.total_input_tokens + Conversation.total_output_tokens), 0),
            func.count(),
            func.max(Conversation.updated_at),
        )
        .where(Conversation.user_id.in_(ids))
        .group_by(Conversation.user_id)
    )
    for uid, cost, markup, tokens, count, last_at in conv_rows:
        a = agg[uid]
        a.total_cost_usd = Decimal(cost or 0)
        a.total_markup_cost_usd = Decimal(markup or 0)
        a.total_tokens = int(tokens or 0)
        a.conversation_count = int(count or 0)
        a.last_conversation_at = last_at

    fb_rows = await db.execute(
        select(UserFeedback.user_id, func.count()).where(UserFeedback.user_id.in_(ids)).group_by(UserFeedback.user_id)
    )
    for uid, count in fb_rows:
        agg[uid].feedback_count = int(count or 0)

    # Average runs = average JSON array length of results_data across the user's
    # experiments.  json_array_length works on both SQLite and PostgreSQL for
    # JSON-typed columns (Experiment.results_data is declared as plain JSON).
    open_case = case((Experiment.status != "completed", 1), else_=0)
    exp_rows = await db.execute(
        select(
            Experiment.user_id,
            func.coalesce(func.sum(open_case), 0),
            func.avg(func.json_array_length(func.coalesce(Experiment.results_data, "[]"))),
        )
        .where(Experiment.user_id.in_(ids))
        .group_by(Experiment.user_id)
    )
    for uid, open_count, avg_runs in exp_rows:
        a = agg[uid]
        a.open_experiments = int(open_count or 0)
        a.avg_runs_per_experiment = float(avg_runs) if avg_runs is not None else None

    bal_rows = await db.execute(
        select(UserBalance.user_id, UserBalance.balance_usd, UserBalance.balance_tokens).where(
            UserBalance.user_id.in_(ids)
        )
    )
    for uid, usd, tokens in bal_rows:
        a = agg[uid]
        a.balance_usd = Decimal(usd) if usd is not None else None
        a.balance_tokens = int(tokens) if tokens is not None else None

    # Signup request join is by lower(email); one signup per email in practice.
    sig_rows = await db.execute(
        select(
            func.lower(SignupRequest.email),
            SignupRequest.status,
            SignupRequest.accepted_disclaimers,
        ).where(func.lower(SignupRequest.email).in_(emails_lower))
    )
    by_email = {email: (status, disc) for email, status, disc in sig_rows}
    for user in users:
        row = by_email.get(user.email.lower())
        if row:
            agg[user.id].signup_status = row[0]
            agg[user.id].disclaimers_accepted = bool(row[1]) if row[1] is not None else None

    return agg


async def set_active(db: AsyncSession, user: User, is_active: bool) -> User:
    """Enable or disable a user. Won't deactivate the last remaining admin."""
    if user.is_admin and not is_active:
        remaining = await count_admins(db)
        if remaining <= 1:
            raise ValueError("Cannot deactivate the last remaining admin")  # noqa: TRY003
    user.is_active = is_active
    await db.flush()
    return user


async def set_role(db: AsyncSession, user: User, role_id: uuid.UUID | None) -> User:
    """Assign a role (or clear it)."""
    user.role_id = role_id
    await db.flush()
    return user
