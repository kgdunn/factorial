"""Tests for cookie-based authentication endpoints and dual auth (cookie + API key).

Uses mocks for the database layer to avoid requiring a running PostgreSQL instance.
"""

from __future__ import annotations

import uuid
from contextlib import contextmanager
from datetime import UTC, datetime, timedelta
from unittest.mock import AsyncMock, patch

import pytest
from httpx import ASGITransport, AsyncClient

from app.api.deps import SESSION_COOKIE_NAME
from app.config import Settings
from app.main import app
from app.services.auth_service import hash_password
from app.services.session_service import NewSession

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
        is_admin: bool = False,
    ):
        self.id = user_id
        self.email = email
        self.password_hash = hash_password(password)
        self.display_name = "Alice"
        self.role_id = None
        self.role = None
        self.is_admin = is_admin
        self.is_active = True
        self.created_at = "2026-01-01T00:00:00+00:00"
        self.updated_at = "2026-01-01T00:00:00+00:00"


class _FakeSession:
    """Mimics a Session ORM row for cookie-auth tests."""

    def __init__(
        self,
        *,
        session_bytes: bytes | None = None,
        user_id: uuid.UUID = _TEST_USER_ID,
        revoked: bool = False,
        idle_offset_days: int = 30,
    ):
        self.id = session_bytes or b"\x01" * 32
        self.public_id = uuid.uuid4()
        self.user_id = user_id
        self.family_id = uuid.uuid4()
        now = datetime.now(UTC)
        self.created_at = now
        self.last_used_at = now
        self.idle_expires_at = now + timedelta(days=idle_offset_days)
        self.absolute_expires_at = now + timedelta(days=180)
        self.revoked_at = now if revoked else None
        self.user_agent = "pytest"
        self.ip = "127.0.0.1"


def _new_session_stub(user_id: uuid.UUID = _TEST_USER_ID) -> NewSession:
    return NewSession(
        cookie_value="dGVzdC1jb29raWUtdmFsdWU",  # arbitrary base64url
        csrf_token="test-csrf-token",  # noqa: S106
        session=_FakeSession(user_id=user_id),
    )


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
    async def test_register_disabled(self, client):
        """Direct registration is disabled — returns 403."""
        resp = await client.post(
            "/api/v1/auth/register",
            json={
                "email": _TEST_EMAIL,
                "password": _TEST_PASSWORD,
                "display_name": "Alice",
                "background": "chemical_engineer",
            },
        )
        assert resp.status_code == 403
        assert "invite only" in resp.json()["detail"].lower()

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


# ---------------------------------------------------------------------------
# Login
# ---------------------------------------------------------------------------


class TestLogin:
    @pytest.mark.asyncio
    async def test_login_success_sets_cookies(self, client):
        """Login with valid credentials sets the session and CSRF cookies."""
        fake_user = _FakeUser()
        mock_auth = AsyncMock(return_value=fake_user)
        mock_session = AsyncMock(return_value=_new_session_stub())

        with (
            patch("app.api.v1.endpoints.auth.authenticate_user", mock_auth),
            patch("app.api.v1.endpoints.auth.session_service.create_session", mock_session),
            patch("app.api.v1.endpoints.auth.balance_service.get_balance", AsyncMock(return_value=None)),
            patch("app.api.v1.endpoints.auth.record_login_activity", AsyncMock()),
        ):
            resp = await client.post(
                "/api/v1/auth/login",
                json={"email": _TEST_EMAIL, "password": _TEST_PASSWORD},
            )
        assert resp.status_code == 200
        # No JWT in body — only the user profile.
        body = resp.json()
        assert "access_token" not in body
        assert "refresh_token" not in body
        assert body["email"] == _TEST_EMAIL
        # Both cookies must be set.
        cookies = resp.headers.get_list("set-cookie")
        joined = " ".join(cookies)
        assert "factorial_session=" in joined
        assert "factorial_csrf=" in joined
        assert "HttpOnly" in joined  # session cookie carries HttpOnly

    @pytest.mark.asyncio
    async def test_login_wrong_password(self, client):
        """Login with wrong password returns 401 and sets no cookie."""
        mock_auth = AsyncMock(return_value=None)

        with patch("app.api.v1.endpoints.auth.authenticate_user", mock_auth):
            resp = await client.post(
                "/api/v1/auth/login",
                json={"email": _TEST_EMAIL, "password": "wrongpassword"},
            )
        assert resp.status_code == 401
        assert "factorial_session" not in (resp.headers.get("set-cookie") or "")


# ---------------------------------------------------------------------------
# /me endpoint (uses dependency override; cookie-agnostic at this layer)
# ---------------------------------------------------------------------------


class TestMe:
    @pytest.mark.asyncio
    async def test_me_returns_user_profile(self, client):
        """GET /me returns the current user's profile (testing bypass)."""
        mock_get = AsyncMock(return_value=None)
        with patch("app.api.v1.endpoints.auth.balance_service.get_balance", mock_get):
            resp = await client.get("/api/v1/auth/me")
        assert resp.status_code == 200
        data = resp.json()
        assert "id" in data
        assert "email" in data
        assert "balance_usd" in data
        assert "balance_tokens" in data

    @pytest.mark.asyncio
    async def test_me_includes_balance_when_present(self, client):
        """GET /me surfaces balance_usd / balance_tokens from the balance service."""
        from decimal import Decimal

        class _FakeBalance:
            def __init__(self, usd: Decimal, tokens: int) -> None:
                self.balance_usd = usd
                self.balance_tokens = tokens

        mock_get = AsyncMock(return_value=_FakeBalance(Decimal("12.3400"), 4_200_000))
        with patch("app.api.v1.endpoints.auth.balance_service.get_balance", mock_get):
            resp = await client.get("/api/v1/auth/me")

        assert resp.status_code == 200
        data = resp.json()
        assert Decimal(data["balance_usd"]) == Decimal("12.3400")
        assert data["balance_tokens"] == 4_200_000

    @pytest.mark.asyncio
    async def test_me_balance_null_when_no_row(self, client):
        """GET /me returns null balance fields when no user_balances row exists."""
        mock_get = AsyncMock(return_value=None)
        with patch("app.api.v1.endpoints.auth.balance_service.get_balance", mock_get):
            resp = await client.get("/api/v1/auth/me")

        assert resp.status_code == 200
        data = resp.json()
        assert data["balance_usd"] is None
        assert data["balance_tokens"] is None


# ---------------------------------------------------------------------------
# Dual auth: cookie + API key
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
    async def test_cookie_works_on_protected_endpoints(self):
        """A valid session cookie is accepted on protected endpoints."""
        fake_user = _FakeUser()
        fake_session = _FakeSession(user_id=fake_user.id)
        test_settings = Settings(app_env="production", api_secret_key="my-secret-key")  # noqa: S106

        with (
            _without_auth_overrides(),
            patch("app.api.deps.settings", test_settings),
            patch(
                "app.api.deps.lookup_session_by_cookie",
                AsyncMock(return_value=fake_session),
            ),
            patch("app.api.deps.get_user_by_id", AsyncMock(return_value=fake_user)),
        ):
            transport = ASGITransport(app=app)
            async with AsyncClient(transport=transport, base_url="http://test") as ac:
                resp = await ac.get(
                    "/api/v1/tools",
                    cookies={SESSION_COOKIE_NAME: "any-cookie-value"},
                )
        assert resp.status_code == 200

    @pytest.mark.asyncio
    async def test_invalid_cookie_falls_back_to_api_key(self):
        """An invalid cookie does not block the API-key fallback."""
        test_settings = Settings(
            app_env="production",
            api_secret_key="my-secret-key",  # noqa: S106
        )

        with (
            _without_auth_overrides(),
            patch("app.api.deps.settings", test_settings),
            patch(
                "app.api.deps.lookup_session_by_cookie",
                AsyncMock(return_value=None),
            ),
        ):
            transport = ASGITransport(app=app)
            async with AsyncClient(transport=transport, base_url="http://test") as ac:
                resp = await ac.get(
                    "/api/v1/tools",
                    cookies={SESSION_COOKIE_NAME: "garbage"},
                    headers={"X-API-Key": "my-secret-key"},
                )
        assert resp.status_code == 200
