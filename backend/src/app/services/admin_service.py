"""Admin user management: bootstrap, promote, demote, list, deactivate."""

from __future__ import annotations

import uuid
from typing import Any

from sqlalchemy import func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.user import User


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
) -> tuple[list[User], int]:
    """Paginated user list for the admin UI."""
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
    return users, total


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
