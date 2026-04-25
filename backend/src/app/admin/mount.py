"""Wire ``sqladmin`` into the FastAPI application."""

from __future__ import annotations

from fastapi import FastAPI
from sqladmin import Admin

from app.admin.auth import AdminAuth
from app.admin.views import ALL_VIEWS
from app.config import settings
from app.db.session import engine


def mount_admin(app: FastAPI) -> Admin:
    """Mount the read-only DB browser at ``/admin``.

    sqladmin installs its own ``SessionMiddleware`` (signed with a
    server secret) when an authentication backend is supplied — no
    extra middleware wiring is needed on the FastAPI app. We reuse
    ``api_secret_key`` as the signing secret: it's already stable
    across deploys, never sent to the browser, and keeps the env
    surface small.
    """
    admin = Admin(
        app,
        engine,
        base_url="/admin",
        title="Factorial admin",
        authentication_backend=AdminAuth(secret_key=settings.api_secret_key),
    )
    for view in ALL_VIEWS:
        admin.add_view(view)
    return admin
