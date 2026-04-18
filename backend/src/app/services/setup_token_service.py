"""Setup / password-reset token service.

Used for both first-time admin bootstrap (``purpose="setup"``) and
password reset for existing users (``purpose="reset"``). A token is
single-use: once ``used_at`` is set, it can no longer be redeemed.
"""

from __future__ import annotations

import secrets
import uuid
from datetime import UTC, datetime, timedelta

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from app.models.setup_token import SetupToken
from app.models.user import User
from app.services.auth_service import hash_password

SETUP = "setup"
RESET = "reset"  # noqa: S105
_VALID_PURPOSES = frozenset({SETUP, RESET})


async def issue_token(db: AsyncSession, user: User, purpose: str) -> SetupToken:
    """Create a new single-use token for the given user."""
    if purpose not in _VALID_PURPOSES:
        raise ValueError(f"Invalid purpose: {purpose}")  # noqa: TRY003

    token = SetupToken(
        user_id=user.id,
        token=secrets.token_urlsafe(32),
        purpose=purpose,
        expires_at=datetime.now(UTC) + timedelta(hours=settings.invite_token_expire_hours),
    )
    db.add(token)
    await db.flush()
    return token


def _ensure_usable(token: SetupToken) -> None:
    if token.used_at is not None:
        raise ValueError("This link has already been used")  # noqa: TRY003
    expires_at = token.expires_at
    if isinstance(expires_at, datetime) and datetime.now(UTC) > expires_at.replace(tzinfo=UTC):
        raise ValueError("This link has expired")  # noqa: TRY003


async def validate_token(db: AsyncSession, raw_token: str) -> tuple[SetupToken, User]:
    """Look up a token, verify it's usable, and return it with its user.

    Raises ValueError on any problem (not found / expired / already used /
    user inactive).
    """
    result = await db.execute(select(SetupToken).where(SetupToken.token == raw_token))
    token = result.scalar_one_or_none()
    if token is None:
        raise ValueError("Invalid link")  # noqa: TRY003
    _ensure_usable(token)

    user = await db.get(User, token.user_id)
    if user is None or not user.is_active:
        raise ValueError("Invalid link")  # noqa: TRY003

    return token, user


async def consume_token(db: AsyncSession, raw_token: str, new_password: str) -> User:
    """Validate the token, set the user's password, mark the token used."""
    token, user = await validate_token(db, raw_token)
    user.password_hash = hash_password(new_password)
    token.used_at = datetime.now(UTC)
    await db.flush()
    return user


async def find_active_user_by_email(db: AsyncSession, email: str) -> User | None:
    """Case-sensitive email lookup for the active user, or None."""
    result = await db.execute(select(User).where(User.email == email, User.is_active.is_(True)))
    return result.scalar_one_or_none()


async def build_setup_url(token: SetupToken) -> str:
    """Build the frontend URL for the given token."""
    path = "/auth/setup" if token.purpose == SETUP else "/auth/reset"
    return f"{settings.frontend_url}{path}?token={token.token}"


async def issue_token_by_user_id(db: AsyncSession, user_id: uuid.UUID, purpose: str) -> SetupToken:
    """Convenience helper: look up a user by id and issue a token."""
    user = await db.get(User, user_id)
    if user is None:
        raise ValueError("User not found")  # noqa: TRY003
    return await issue_token(db, user, purpose)
