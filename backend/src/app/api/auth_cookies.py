"""Helpers for setting and clearing the session + CSRF cookies.

Centralised so login, invite-register, and password-setup endpoints all
emit identical ``Set-Cookie`` headers. Anything cookie-shaped that is
not these helpers is a bug.
"""

from __future__ import annotations

from datetime import timedelta

from fastapi import Response

from app.api.csrf import CSRF_COOKIE_NAME
from app.api.deps import SESSION_COOKIE_NAME
from app.config import settings


def set_session_cookies(
    response: Response,
    *,
    session_cookie_value: str,
    csrf_token: str,
) -> None:
    """Emit both the httpOnly session cookie and the JS-readable CSRF cookie.

    Lifetime tracks the absolute session expiry; idle expiry is enforced
    server-side at lookup time. ``Secure`` is gated on production so dev
    over plain http://localhost still works.
    """
    max_age = int(timedelta(days=settings.cookie_session_absolute_days).total_seconds())

    response.set_cookie(
        key=SESSION_COOKIE_NAME,
        value=session_cookie_value,
        max_age=max_age,
        httponly=True,
        secure=settings.cookie_secure,
        samesite="lax",
        path="/",
    )
    response.set_cookie(
        key=CSRF_COOKIE_NAME,
        value=csrf_token,
        max_age=max_age,
        httponly=False,  # JS reads this and mirrors into X-CSRF-Token
        secure=settings.cookie_secure,
        samesite="lax",
        path="/",
    )


def clear_session_cookies(response: Response) -> None:
    """Expire both cookies. Used by /auth/logout."""
    response.delete_cookie(SESSION_COOKIE_NAME, path="/")
    response.delete_cookie(CSRF_COOKIE_NAME, path="/")
