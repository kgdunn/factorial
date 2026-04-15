"""Shared FastAPI dependencies for authentication and authorization.

Interim security: API-key-based authentication via ``X-API-Key`` header.
When the full JWT auth system (Feature 5) is implemented, replace
``require_api_key`` with a JWT token validator.
"""

import hmac

from fastapi import HTTPException, Security, status
from fastapi.security import APIKeyHeader

from app.config import settings

_api_key_header = APIKeyHeader(name="X-API-Key", auto_error=False)


async def require_api_key(
    api_key: str | None = Security(_api_key_header),
) -> str:
    """Validate the ``X-API-Key`` header against the configured secret.

    Bypassed when ``APP_ENV=testing`` so existing tests pass without
    sending an API key.
    """
    if settings.app_env == "testing":
        return "testing-bypass"

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
