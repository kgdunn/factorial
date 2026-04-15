"""Shared FastAPI dependencies for authentication and authorization.

Dual auth: JWT Bearer tokens (for browser users) and API key (for
machine-to-machine / service-to-service calls).  ``require_auth``
tries JWT first, falls back to API key, and returns an ``AuthUser``
in both cases.
"""

from __future__ import annotations

import hmac
import uuid
from dataclasses import dataclass, field

from fastapi import Depends, HTTPException, Security, status
from fastapi.security import APIKeyHeader, OAuth2PasswordBearer
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from app.db.session import get_db_session
from app.services.auth_service import decode_token, get_user_by_id

# ---------------------------------------------------------------------------
# AuthUser — lightweight identity object returned by require_auth
# ---------------------------------------------------------------------------


@dataclass
class AuthUser:
    """Lightweight user identity extracted from JWT or API key auth.

    Used instead of the SQLAlchemy ``User`` model so synthetic users
    (testing bypass, API-key service accounts) can be created without
    a database session.
    """

    id: uuid.UUID
    email: str
    display_name: str | None = None
    background: str | None = None
    is_active: bool = True
    is_service_account: bool = field(default=False)


# ---------------------------------------------------------------------------
# Security schemes
# ---------------------------------------------------------------------------

_api_key_header = APIKeyHeader(name="X-API-Key", auto_error=False)
_oauth2_scheme = OAuth2PasswordBearer(tokenUrl="/api/v1/auth/login", auto_error=False)

# A fixed UUID for the synthetic "service" user created by API-key auth.
SERVICE_USER_ID = uuid.UUID("00000000-0000-0000-0000-000000000000")

# A fixed UUID for the testing bypass user.
TESTING_USER_ID = uuid.UUID("00000000-0000-0000-0000-000000000001")


# ---------------------------------------------------------------------------
# Synthetic users
# ---------------------------------------------------------------------------


def _testing_user() -> AuthUser:
    """Return a synthetic user for the testing environment."""
    return AuthUser(
        id=TESTING_USER_ID,
        email="test@example.com",
        display_name="Test User",
        is_service_account=True,
    )


def _service_user() -> AuthUser:
    """Return a synthetic user for API-key authenticated requests."""
    return AuthUser(
        id=SERVICE_USER_ID,
        email="service@internal",
        display_name="Service Account",
        is_service_account=True,
    )


# ---------------------------------------------------------------------------
# API key auth (machine-to-machine)
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
# JWT auth (browser users)
# ---------------------------------------------------------------------------


async def get_current_user(
    token: str | None = Security(_oauth2_scheme),
    db: AsyncSession = Depends(get_db_session),
) -> AuthUser | None:
    """Extract and validate JWT token, return an AuthUser or None."""
    if not token:
        return None

    try:
        payload = decode_token(token)
    except Exception:  # noqa: BLE001
        return None

    if payload.get("type") != "access":
        return None

    try:
        user_id = uuid.UUID(payload["sub"])
    except (KeyError, ValueError):
        return None

    user = await get_user_by_id(db, user_id)
    if not user or not user.is_active:
        return None

    return AuthUser(
        id=user.id,
        email=user.email,
        display_name=user.display_name,
        background=user.background,
        is_active=user.is_active,
    )


# ---------------------------------------------------------------------------
# Dual auth: JWT or API key
# ---------------------------------------------------------------------------


async def require_auth(
    jwt_user: AuthUser | None = Depends(get_current_user),
    api_key: str | None = Security(_api_key_header),
) -> AuthUser:
    """Require either a valid JWT token or a valid API key.

    Returns an ``AuthUser`` in both cases:
    - JWT auth: built from the real database user.
    - API key auth: a synthetic "service" user.

    Raises 401 if neither authentication method succeeds.
    """
    # JWT auth succeeded
    if jwt_user is not None:
        return jwt_user

    # Fall back to API key
    if api_key and settings.api_secret_key and hmac.compare_digest(api_key, settings.api_secret_key):
        return _service_user()

    raise HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Not authenticated",
        headers={"WWW-Authenticate": "Bearer, ApiKey"},
    )
