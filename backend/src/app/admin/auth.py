"""Authentication backend for the sqladmin DB browser.

Bridges sqladmin's session-cookie auth into the existing ``users``
table: a successful ``/admin/login`` requires a row in ``users`` with
matching bcrypt password, ``is_active = true``, and ``is_admin = true``.
Non-admins are rejected at login. Demoted or deactivated admins are
also rejected on every subsequent request because ``authenticate``
re-fetches the user.
"""

from __future__ import annotations

import uuid

from sqladmin.authentication import AuthenticationBackend
from starlette.requests import Request

from app.db.session import async_session_factory
from app.services.auth_service import authenticate_user, get_user_by_id

_SESSION_USER_KEY = "admin_user_id"


class AdminAuth(AuthenticationBackend):
    """Validate operators against the ``users`` table + ``is_admin``."""

    async def login(self, request: Request) -> bool:
        form = await request.form()
        email = str(form.get("username", "")).strip().lower()
        password = str(form.get("password", ""))
        if not email or not password:
            return False

        async with async_session_factory() as db:
            user = await authenticate_user(db, email, password)
            if user is None or not user.is_admin:
                return False
            request.session[_SESSION_USER_KEY] = str(user.id)
        return True

    async def logout(self, request: Request) -> bool:
        request.session.clear()
        return True

    async def authenticate(self, request: Request) -> bool:
        raw = request.session.get(_SESSION_USER_KEY)
        if not raw:
            return False
        try:
            user_id = uuid.UUID(raw)
        except (TypeError, ValueError):
            return False

        async with async_session_factory() as db:
            user = await get_user_by_id(db, user_id)
        return user is not None and user.is_active and user.is_admin
