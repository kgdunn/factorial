"""Browser session service.

Sessions are opaque DB rows. The cookie carries a 32-byte random ``id``
(base64url-encoded on the wire) which is looked up directly. There is no
JWT, no signing key, no per-process state.

Lifecycle:
- ``create_session`` mints a row + a CSRF token, returns the cookie value
  and CSRF value to be ``Set-Cookie``-d by the caller.
- ``lookup_session_by_cookie`` validates the cookie and returns the row
  if it's still alive (not revoked, not idle-expired, not absolute-
  expired), and write-throttles ``last_used_at`` to once a minute to
  avoid amplifying writes on hot paths.
- ``revoke_session`` revokes a single session; ``revoke_family`` revokes
  every session in the same family (sign-out-everywhere).

The CSRF cookie value is independent of the session id — double-submit
just compares the header to the cookie via ``hmac.compare_digest``. We
return a CSRF token here purely so the caller can ``Set-Cookie`` it
alongside the session cookie at login time.
"""

from __future__ import annotations

import base64
import hmac
import secrets
import uuid
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta

from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from app.models.session import Session

_SESSION_ID_BYTES = 32
_CSRF_TOKEN_BYTES = 32
_LAST_USED_THROTTLE = timedelta(minutes=1)


@dataclass(frozen=True)
class NewSession:
    """Returned from ``create_session`` so the endpoint can set cookies."""

    cookie_value: str  # base64url-encoded session id, goes in Set-Cookie
    csrf_token: str  # base64url-encoded random, mirrored client-side
    session: Session


def _encode_id(raw: bytes) -> str:
    return base64.urlsafe_b64encode(raw).rstrip(b"=").decode("ascii")


def _decode_id(value: str) -> bytes | None:
    """Decode a cookie value back to raw bytes, or None if malformed."""
    try:
        padding = "=" * ((4 - len(value) % 4) % 4)
        raw = base64.urlsafe_b64decode(value + padding)
    except (ValueError, TypeError):
        return None
    if len(raw) != _SESSION_ID_BYTES:
        return None
    return raw


async def create_session(
    db: AsyncSession,
    *,
    user_id: uuid.UUID,
    user_agent: str | None,
    ip: str | None,
    family_id: uuid.UUID | None = None,
) -> NewSession:
    """Mint a new session row and the matching CSRF token.

    Pass ``family_id`` to opt this session into an existing family (used
    when an authenticated user opens a new device while keeping their
    "logout-everywhere" grouping); otherwise a fresh family is created.
    """
    raw_id = secrets.token_bytes(_SESSION_ID_BYTES)
    csrf_token = secrets.token_urlsafe(_CSRF_TOKEN_BYTES)
    now = datetime.now(UTC)
    session = Session(
        id=raw_id,
        user_id=user_id,
        family_id=family_id or uuid.uuid4(),
        created_at=now,
        last_used_at=now,
        idle_expires_at=now + timedelta(days=settings.cookie_session_idle_days),
        absolute_expires_at=now + timedelta(days=settings.cookie_session_absolute_days),
        user_agent=(user_agent or "")[:256] or None,
        ip=ip,
    )
    db.add(session)
    await db.flush()
    return NewSession(
        cookie_value=_encode_id(raw_id),
        csrf_token=csrf_token,
        session=session,
    )


async def lookup_session_by_cookie(
    db: AsyncSession,
    cookie_value: str,
) -> Session | None:
    """Return the session row backing a cookie, or None if invalid.

    Validates revoked / idle / absolute expiry. Touches ``last_used_at``
    and ``idle_expires_at`` at most once per minute per session.
    """
    raw_id = _decode_id(cookie_value)
    if raw_id is None:
        return None

    result = await db.execute(select(Session).where(Session.id == raw_id))
    session = result.scalar_one_or_none()
    if session is None:
        return None

    now = datetime.now(UTC)
    if session.revoked_at is not None:
        return None
    if session.absolute_expires_at <= now:
        return None
    if session.idle_expires_at <= now:
        return None

    if now - session.last_used_at > _LAST_USED_THROTTLE:
        session.last_used_at = now
        session.idle_expires_at = now + timedelta(days=settings.cookie_session_idle_days)
        await db.flush()

    return session


async def revoke_session(db: AsyncSession, session_id: bytes) -> None:
    """Mark a session as revoked. Idempotent."""
    await db.execute(
        update(Session)
        .where(Session.id == session_id, Session.revoked_at.is_(None))
        .values(revoked_at=datetime.now(UTC)),
    )


async def revoke_family(db: AsyncSession, family_id: uuid.UUID) -> int:
    """Revoke every active session in a family. Returns rows affected."""
    result = await db.execute(
        update(Session)
        .where(Session.family_id == family_id, Session.revoked_at.is_(None))
        .values(revoked_at=datetime.now(UTC)),
    )
    return result.rowcount or 0


async def list_user_sessions(db: AsyncSession, user_id: uuid.UUID) -> list[Session]:
    """All non-revoked, non-expired sessions for a user, newest first."""
    now = datetime.now(UTC)
    result = await db.execute(
        select(Session)
        .where(
            Session.user_id == user_id,
            Session.revoked_at.is_(None),
            Session.idle_expires_at > now,
            Session.absolute_expires_at > now,
        )
        .order_by(Session.last_used_at.desc()),
    )
    return list(result.scalars().all())


def csrf_tokens_match(header_value: str | None, cookie_value: str | None) -> bool:
    """Constant-time compare of header and cookie CSRF tokens."""
    if not header_value or not cookie_value:
        return False
    return hmac.compare_digest(header_value, cookie_value)
