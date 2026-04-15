"""Tests for JWT authentication endpoints and dual auth (JWT + API key).

Uses mocks for the database layer to avoid requiring a running PostgreSQL instance.
"""

from __future__ import annotations

import uuid
from contextlib import contextmanager
from unittest.mock import AsyncMock, patch

import pytest
from httpx import ASGITransport, AsyncClient

from app.config import Settings
from app.main import app
from app.services.auth_service import (
    create_access_token,
    create_refresh_token,
    hash_password,
)

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

_TEST_USER_ID = uuid.uuid4()
_TEST_EMAIL = "alice@example.com"
_TEST_PASSWORD = "securepass123"  # noqa: S105


class _FakeUser:
    """Mimics a User ORM object for testing."""

    def __init__(
        self,
        user_id: uuid.UUID = _TEST_USER_ID,
        email: str = _TEST_EMAIL,
        password: str = _TEST_PASSWORD,
    ):
        self.id = user_id
        self.email = email
        self.password_hash = hash_password(password)
        self.display_name = "Alice"
        self.background = "chemical_engineer"
        self.is_active = True
        self.created_at = "2026-01-01T00:00:00+00:00"
        self.updated_at = "2026-01-01T00:00:00+00:00"


@contextmanager
def _without_auth_overrides():
    """Temporarily clear dependency overrides so real auth logic runs."""
    saved = dict(app.dependency_overrides)
    app.dependency_overrides.clear()
    try:
        yield
    finally:
        app.dependency_overrides.update(saved)


# ---------------------------------------------------------------------------
# Registration
# ---------------------------------------------------------------------------


class TestRegister:
    @pytest.mark.asyncio
    async def test_register_success(self, client):
        """Registration with valid data returns 201 + tokens."""
        fake_user = _FakeUser()
        mock_register = AsyncMock(return_value=fake_user)
        mock_db = AsyncMock()

        with (
            patch("app.api.v1.endpoints.auth.register_user", mock_register),
            patch("app.db.session.get_db_session", return_value=mock_db),
        ):
            resp = await client.post(
                "/api/v1/auth/register",
                json={
                    "email": _TEST_EMAIL,
                    "password": _TEST_PASSWORD,
                    "display_name": "Alice",
                    "background": "chemical_engineer",
                },
            )
        assert resp.status_code == 201
        data = resp.json()
        assert "access_token" in data
        assert "refresh_token" in data
        assert data["token_type"] == "bearer"

    @pytest.mark.asyncio
    async def test_register_short_password(self, client):
        """Password shorter than 8 chars returns 422."""
        resp = await client.post(
            "/api/v1/auth/register",
            json={"email": "user@example.com", "password": "short"},
        )
        assert resp.status_code == 422

    @pytest.mark.asyncio
    async def test_register_invalid_email(self, client):
        """Invalid email format returns 422."""
        resp = await client.post(
            "/api/v1/auth/register",
            json={"email": "not-an-email", "password": _TEST_PASSWORD},
        )
        assert resp.status_code == 422

    @pytest.mark.asyncio
    async def test_register_duplicate_email(self, client):
        """Registering an existing email returns 409."""
        mock_register = AsyncMock(side_effect=ValueError("Email already registered"))

        with patch("app.api.v1.endpoints.auth.register_user", mock_register):
            resp = await client.post(
                "/api/v1/auth/register",
                json={"email": _TEST_EMAIL, "password": _TEST_PASSWORD},
            )
        assert resp.status_code == 409


# ---------------------------------------------------------------------------
# Login
# ---------------------------------------------------------------------------


class TestLogin:
    @pytest.mark.asyncio
    async def test_login_success(self, client):
        """Login with valid credentials returns tokens."""
        fake_user = _FakeUser()
        mock_auth = AsyncMock(return_value=fake_user)

        with patch("app.api.v1.endpoints.auth.authenticate_user", mock_auth):
            resp = await client.post(
                "/api/v1/auth/login",
                json={"email": _TEST_EMAIL, "password": _TEST_PASSWORD},
            )
        assert resp.status_code == 200
        data = resp.json()
        assert "access_token" in data
        assert "refresh_token" in data

    @pytest.mark.asyncio
    async def test_login_wrong_password(self, client):
        """Login with wrong password returns 401."""
        mock_auth = AsyncMock(return_value=None)

        with patch("app.api.v1.endpoints.auth.authenticate_user", mock_auth):
            resp = await client.post(
                "/api/v1/auth/login",
                json={"email": _TEST_EMAIL, "password": "wrongpassword"},
            )
        assert resp.status_code == 401

    @pytest.mark.asyncio
    async def test_login_nonexistent_user(self, client):
        """Login with unknown email returns 401."""
        mock_auth = AsyncMock(return_value=None)

        with patch("app.api.v1.endpoints.auth.authenticate_user", mock_auth):
            resp = await client.post(
                "/api/v1/auth/login",
                json={"email": "nobody@example.com", "password": _TEST_PASSWORD},
            )
        assert resp.status_code == 401


# ---------------------------------------------------------------------------
# Token refresh
# ---------------------------------------------------------------------------


class TestTokenRefresh:
    @pytest.mark.asyncio
    async def test_refresh_success(self, client):
        """Valid refresh token returns new token pair."""
        fake_user = _FakeUser()
        refresh_token = create_refresh_token(fake_user.id)
        mock_get = AsyncMock(return_value=fake_user)

        with patch("app.api.v1.endpoints.auth.get_user_by_id", mock_get):
            resp = await client.post(
                "/api/v1/auth/refresh",
                json={"refresh_token": refresh_token},
            )
        assert resp.status_code == 200
        data = resp.json()
        assert "access_token" in data
        assert "refresh_token" in data

    @pytest.mark.asyncio
    async def test_refresh_invalid_token(self, client):
        """Invalid refresh token returns 401."""
        resp = await client.post(
            "/api/v1/auth/refresh",
            json={"refresh_token": "invalid.token.here"},
        )
        assert resp.status_code == 401

    @pytest.mark.asyncio
    async def test_refresh_with_access_token_fails(self, client):
        """Using an access token as a refresh token returns 401."""
        fake_user = _FakeUser()
        access_token = create_access_token(fake_user.id, fake_user.email)

        resp = await client.post(
            "/api/v1/auth/refresh",
            json={"refresh_token": access_token},
        )
        assert resp.status_code == 401


# ---------------------------------------------------------------------------
# /me endpoint
# ---------------------------------------------------------------------------


class TestMe:
    @pytest.mark.asyncio
    async def test_me_returns_user_profile(self, client):
        """GET /me returns the current user's profile (testing bypass)."""
        resp = await client.get("/api/v1/auth/me")
        assert resp.status_code == 200
        data = resp.json()
        assert "id" in data
        assert "email" in data


# ---------------------------------------------------------------------------
# Dual auth: JWT + API key
# ---------------------------------------------------------------------------


class TestDualAuth:
    @pytest.mark.asyncio
    async def test_api_key_still_works_on_protected_endpoints(self):
        """API key authentication still works for protected endpoints."""
        test_settings = Settings(app_env="production", api_secret_key="my-secret-key")  # noqa: S106
        with _without_auth_overrides(), patch("app.api.deps.settings", test_settings):
            transport = ASGITransport(app=app)
            async with AsyncClient(transport=transport, base_url="http://test") as ac:
                resp = await ac.get(
                    "/api/v1/tools",
                    headers={"X-API-Key": "my-secret-key"},
                )
        assert resp.status_code == 200

    @pytest.mark.asyncio
    async def test_no_auth_returns_401_in_production(self):
        """No auth at all returns 401 in production."""
        test_settings = Settings(app_env="production", api_secret_key="my-secret-key")  # noqa: S106
        with _without_auth_overrides(), patch("app.api.deps.settings", test_settings):
            transport = ASGITransport(app=app)
            async with AsyncClient(transport=transport, base_url="http://test") as ac:
                resp = await ac.get("/api/v1/tools")
        assert resp.status_code == 401

    @pytest.mark.asyncio
    async def test_jwt_works_on_protected_endpoints(self):
        """JWT Bearer token is accepted on protected endpoints."""
        fake_user = _FakeUser()
        access_token = create_access_token(fake_user.id, fake_user.email)
        mock_get = AsyncMock(return_value=fake_user)
        test_settings = Settings(app_env="production", api_secret_key="my-secret-key")  # noqa: S106

        with (
            _without_auth_overrides(),
            patch("app.api.deps.settings", test_settings),
            patch("app.api.deps.get_user_by_id", mock_get),
        ):
            transport = ASGITransport(app=app)
            async with AsyncClient(transport=transport, base_url="http://test") as ac:
                resp = await ac.get(
                    "/api/v1/tools",
                    headers={"Authorization": f"Bearer {access_token}"},
                )
        assert resp.status_code == 200

    @pytest.mark.asyncio
    async def test_invalid_jwt_falls_back_to_api_key(self):
        """Invalid JWT doesn't block API key fallback."""
        test_settings = Settings(
            app_env="production",
            api_secret_key="my-secret-key",  # noqa: S106
        )

        with _without_auth_overrides(), patch("app.api.deps.settings", test_settings):
            transport = ASGITransport(app=app)
            async with AsyncClient(transport=transport, base_url="http://test") as ac:
                resp = await ac.get(
                    "/api/v1/tools",
                    headers={
                        "Authorization": "Bearer invalid-token",
                        "X-API-Key": "my-secret-key",
                    },
                )
        assert resp.status_code == 200
