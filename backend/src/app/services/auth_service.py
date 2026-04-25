"""Authentication service: password hashing and user CRUD.

JWT minting and decoding lived here previously; both are gone now that
the browser path uses opaque session cookies (see
``services/session_service.py``).
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime

import bcrypt
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.user import User

# ---------------------------------------------------------------------------
# Password hashing
# ---------------------------------------------------------------------------

# bcrypt only looks at the first 72 bytes of input. passlib used to silently
# truncate; bcrypt >= 4.1 raises. We truncate here to preserve bit-compatibility
# with hashes already stored in the DB from the passlib era.
_BCRYPT_MAX_BYTES = 72


def hash_password(password: str) -> str:
    """Hash a plaintext password with bcrypt."""
    pw_bytes = password.encode("utf-8")[:_BCRYPT_MAX_BYTES]
    return bcrypt.hashpw(pw_bytes, bcrypt.gensalt()).decode("utf-8")


def verify_password(plain_password: str, hashed_password: str) -> bool:
    """Verify a plaintext password against a bcrypt hash."""
    pw_bytes = plain_password.encode("utf-8")[:_BCRYPT_MAX_BYTES]
    return bcrypt.checkpw(pw_bytes, hashed_password.encode("utf-8"))


# ---------------------------------------------------------------------------
# User CRUD
# ---------------------------------------------------------------------------


async def register_user(
    db: AsyncSession,
    email: str,
    password: str,
    display_name: str | None = None,
) -> User:
    """Create a new user account.

    Raises
    ------
    ValueError
        If the email is already registered.
    """
    result = await db.execute(select(User).where(User.email == email))
    if result.scalar_one_or_none():
        raise ValueError("Email already registered")  # noqa: TRY003

    user = User(
        email=email,
        password_hash=hash_password(password),
        display_name=display_name,
    )
    db.add(user)
    await db.flush()
    return user


async def authenticate_user(
    db: AsyncSession,
    email: str,
    password: str,
) -> User | None:
    """Verify credentials and return the user, or None if invalid."""
    result = await db.execute(select(User).where(User.email == email))
    user = result.scalar_one_or_none()
    # Empty ``password_hash`` means the account was created via the CLI and is
    # still awaiting first-time setup; it must not authenticate.
    if not user or not user.password_hash:
        return None
    if not verify_password(password, user.password_hash):
        return None
    if not user.is_active:
        return None
    return user


async def get_user_by_id(db: AsyncSession, user_id: uuid.UUID) -> User | None:
    """Fetch a user by primary key."""
    return await db.get(User, user_id)


async def record_login_activity(
    db: AsyncSession,
    user: User,
    *,
    ip: str | None = None,
    timezone: str | None = None,
) -> None:
    """Stamp the user row with sign-in metadata.

    Best-effort: GeoIP errors never surface, and IP/timezone inputs are
    applied only when non-empty so a refresh from a mobile client without
    timezone doesn't blank out a previously-recorded value.
    """
    from app.services.geoip_service import lookup_country  # local import to avoid cycle

    user.last_login_at = datetime.now(UTC)
    if ip:
        user.last_login_ip = ip
        country = lookup_country(ip)
        if country:
            user.country = country
    if timezone:
        user.timezone = timezone
    await db.flush()
