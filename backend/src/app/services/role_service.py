"""Roles service: list, create, update, delete."""

from __future__ import annotations

import re
import uuid

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.role import Role
from app.models.user import User

_SLUG_RE = re.compile(r"^[a-z0-9_]+$")


def normalize_slug(raw: str) -> str:
    """Lowercase + underscores.  Any other char is rejected by validate_slug."""
    return raw.strip().lower().replace(" ", "_").replace("-", "_")


def validate_slug(slug: str) -> None:
    if not slug:
        raise ValueError("Role name is required")  # noqa: TRY003
    if len(slug) > 50:
        raise ValueError("Role name must be 50 characters or fewer")  # noqa: TRY003
    if not _SLUG_RE.match(slug):
        raise ValueError("Role name must be lowercase letters, digits, or underscores")  # noqa: TRY003


async def list_roles(db: AsyncSession) -> list[Role]:
    result = await db.execute(select(Role).order_by(Role.is_builtin.desc(), Role.name.asc()))
    return list(result.scalars().all())


async def get_role(db: AsyncSession, role_id: uuid.UUID) -> Role | None:
    return await db.get(Role, role_id)


async def get_role_by_name(db: AsyncSession, name: str) -> Role | None:
    result = await db.execute(select(Role).where(Role.name == name))
    return result.scalar_one_or_none()


async def create_role(db: AsyncSession, name: str, description: str | None) -> Role:
    slug = normalize_slug(name)
    validate_slug(slug)
    existing = await get_role_by_name(db, slug)
    if existing is not None:
        raise ValueError(f"Role '{slug}' already exists")  # noqa: TRY003

    role = Role(name=slug, description=description, is_builtin=False)
    db.add(role)
    await db.flush()
    return role


async def update_role(db: AsyncSession, role: Role, description: str | None) -> Role:
    """Only the description is mutable once a role exists."""
    role.description = description
    await db.flush()
    return role


async def delete_role(db: AsyncSession, role: Role) -> None:
    if role.is_builtin:
        raise ValueError("Built-in roles cannot be deleted")  # noqa: TRY003

    user_count = await db.execute(select(func.count()).select_from(User).where(User.role_id == role.id))
    if user_count.scalar_one() > 0:
        raise ValueError("Role is in use by one or more users")  # noqa: TRY003

    await db.delete(role)
    await db.flush()
