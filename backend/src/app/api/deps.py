"""Shared FastAPI dependencies for authentication and authorization.

Dual auth: opaque session cookie (for browser users) and API key (for
machine-to-machine / service-to-service calls). ``require_auth`` tries
the cookie first, falls back to the API key, and returns an
``AuthUser`` in both cases.

The session id in the ``factorial_session`` cookie is opaque random
bytes that map directly to a row in the ``sessions`` table; there is no
signing key in the loop, so server redeploys do not invalidate any
browser session.
"""

from __future__ import annotations

import hmac
import uuid
from dataclasses import dataclass

from fastapi import Depends, HTTPException, Request, Security, status
from fastapi.security import APIKeyHeader
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from app.db.session import get_db_session
from app.services.auth_service import get_user_by_id
from app.services.session_service import lookup_session_by_cookie

SESSION_COOKIE_NAME = "factorial_session"


@dataclass
class AuthUser:
    """Lightweight user identity extracted from cookie or API-key auth.

    Used instead of the SQLAlchemy ``User`` model so synthetic users
    (API-key service user) can be created without a database row.
    ``background`` is the role slug (from the ``roles`` table) that
    personalises the LLM system prompt. ``session_id`` is set for
    cookie-authed users and is None for the synthetic service user; it
    lets endpoints that revoke the *current* session (logout) know
    which row to revoke.
    """

    id: uuid.UUID
    email: str
    display_name: str | None = None
    background: str | None = None
    is_active: bool = True
    is_admin: bool = False
    session_id: bytes | None = None
    family_id: uuid.UUID | None = None


_api_key_header = APIKeyHeader(name="X-API-Key", auto_error=False)

# A fixed UUID for the synthetic "service" user created by API-key auth.
SERVICE_USER_ID = uuid.UUID("00000000-0000-0000-0000-000000000000")

# A fixed UUID for the testing bypass user.
TESTING_USER_ID = uuid.UUID("00000000-0000-0000-0000-000000000001")


def _service_user() -> AuthUser:
    """Return a synthetic user for API-key authenticated requests."""
    return AuthUser(
        id=SERVICE_USER_ID,
        email="service@internal",
        display_name="Service Account",
    )


# ---------------------------------------------------------------------------
# API-key auth (machine-to-machine)
# ---------------------------------------------------------------------------


async def require_api_key(
    api_key: str | None = Security(_api_key_header),
) -> str:
    """Validate the ``X-API-Key`` header against the configured secret."""
    if not settings.api_secret_key:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="API key not configured on server",
        )

    if not api_key or not hmac.compare_digest(api_key, settings.api_secret_key):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid or missing API key",
            headers={"WWW-Authenticate": "ApiKey"},
        )

    return api_key


# ---------------------------------------------------------------------------
# Session-cookie auth (browser users)
# ---------------------------------------------------------------------------


async def get_current_user(
    request: Request,
    db: AsyncSession = Depends(get_db_session),
) -> AuthUser | None:
    """Resolve the session cookie to an ``AuthUser`` or None."""
    cookie_value = request.cookies.get(SESSION_COOKIE_NAME)
    if not cookie_value:
        return None

    session = await lookup_session_by_cookie(db, cookie_value)
    if session is None:
        return None

    user = await get_user_by_id(db, session.user_id)
    if not user or not user.is_active:
        return None

    role_slug: str | None = user.role.name if user.role_id is not None and user.role is not None else None

    return AuthUser(
        id=user.id,
        email=user.email,
        display_name=user.display_name,
        background=role_slug,
        is_active=user.is_active,
        is_admin=user.is_admin,
        session_id=session.id,
        family_id=session.family_id,
    )


# ---------------------------------------------------------------------------
# Dual auth: cookie or API key
# ---------------------------------------------------------------------------


async def require_auth(
    cookie_user: AuthUser | None = Depends(get_current_user),
    api_key: str | None = Security(_api_key_header),
) -> AuthUser:
    """Require either a valid session cookie or a valid API key.

    Returns an ``AuthUser`` in both cases:
    - cookie auth: built from the real database user.
    - API-key auth: a synthetic "service" user.

    Raises 401 if neither authentication method succeeds.
    """
    if cookie_user is not None:
        return cookie_user

    if api_key and settings.api_secret_key and hmac.compare_digest(api_key, settings.api_secret_key):
        return _service_user()

    raise HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Not authenticated",
        headers={"WWW-Authenticate": "Cookie, ApiKey"},
    )


# ---------------------------------------------------------------------------
# Admin authorization
# ---------------------------------------------------------------------------


async def require_admin(
    current_user: AuthUser = Depends(require_auth),
) -> AuthUser:
    """Require the current user to be an admin (``users.is_admin`` true)."""
    if not current_user.is_admin:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Admin access required")
    return current_user
