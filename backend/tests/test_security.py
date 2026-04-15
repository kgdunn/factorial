"""Tests for interim security hardening: API key auth, docs suppression, CORS, rate limiting."""

from __future__ import annotations

from unittest.mock import patch

import pytest
from fastapi import Depends, FastAPI
from httpx import ASGITransport, AsyncClient

from app.api.deps import require_api_key
from app.config import Settings

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_protected_app(app_env: str, api_secret_key: str) -> FastAPI:
    """Build a minimal FastAPI app with ``require_api_key`` wired up,
    using the given settings overrides."""
    test_settings = Settings(app_env=app_env, api_secret_key=api_secret_key)

    test_app = FastAPI()

    @test_app.get("/protected")
    async def _protected(key: str = Depends(require_api_key)):  # noqa: ARG001
        return {"ok": True}

    # Patch the settings used inside require_api_key
    test_app._security_settings_patch = test_settings  # noqa: SLF001
    return test_app


# ---------------------------------------------------------------------------
# API key — testing bypass
# ---------------------------------------------------------------------------


class TestApiKeyTestingBypass:
    """In APP_ENV=testing the API key check is bypassed."""

    @pytest.mark.asyncio
    async def test_health_no_key_required(self, client):
        resp = await client.get("/api/v1/health")
        assert resp.status_code == 200

    @pytest.mark.asyncio
    async def test_protected_endpoint_works_without_key_in_testing(self, client):
        resp = await client.get("/api/v1/tools")
        assert resp.status_code == 200


# ---------------------------------------------------------------------------
# API key — production enforcement
# ---------------------------------------------------------------------------


class TestApiKeyProductionEnforcement:
    """When APP_ENV != testing, the API key must be present and correct."""

    @pytest.mark.asyncio
    async def test_missing_key_returns_401(self):
        test_settings = Settings(app_env="production", api_secret_key="correct-key")  # noqa: S106
        with patch("app.api.deps.settings", test_settings):
            app = _make_protected_app("production", "correct-key")
            transport = ASGITransport(app=app)
            async with AsyncClient(transport=transport, base_url="http://test") as ac:
                resp = await ac.get("/protected")
        assert resp.status_code == 401

    @pytest.mark.asyncio
    async def test_wrong_key_returns_401(self):
        test_settings = Settings(app_env="production", api_secret_key="correct-key")  # noqa: S106
        with patch("app.api.deps.settings", test_settings):
            app = _make_protected_app("production", "correct-key")
            transport = ASGITransport(app=app)
            async with AsyncClient(transport=transport, base_url="http://test") as ac:
                resp = await ac.get("/protected", headers={"X-API-Key": "wrong-key"})
        assert resp.status_code == 401

    @pytest.mark.asyncio
    async def test_valid_key_returns_200(self):
        test_settings = Settings(app_env="production", api_secret_key="correct-key")  # noqa: S106
        with patch("app.api.deps.settings", test_settings):
            app = _make_protected_app("production", "correct-key")
            transport = ASGITransport(app=app)
            async with AsyncClient(transport=transport, base_url="http://test") as ac:
                resp = await ac.get("/protected", headers={"X-API-Key": "correct-key"})
        assert resp.status_code == 200
        assert resp.json() == {"ok": True}

    @pytest.mark.asyncio
    async def test_unconfigured_key_returns_500(self):
        test_settings = Settings(app_env="production", api_secret_key="")
        with patch("app.api.deps.settings", test_settings):
            app = _make_protected_app("production", "")
            transport = ASGITransport(app=app)
            async with AsyncClient(transport=transport, base_url="http://test") as ac:
                resp = await ac.get("/protected", headers={"X-API-Key": "anything"})
        assert resp.status_code == 500


# ---------------------------------------------------------------------------
# Docs suppression
# ---------------------------------------------------------------------------


class TestDocsSuppression:
    """OpenAPI docs should be available in testing but disabled in production."""

    @pytest.mark.asyncio
    async def test_docs_available_in_testing(self, client):
        resp = await client.get("/docs")
        assert resp.status_code == 200

    @pytest.mark.asyncio
    async def test_openapi_json_available_in_testing(self, client):
        resp = await client.get("/openapi.json")
        assert resp.status_code == 200


# ---------------------------------------------------------------------------
# CORS configuration
# ---------------------------------------------------------------------------


class TestCorsConfig:
    """CORS settings should be restrictive in production, permissive in dev."""

    def test_production_methods_restricted(self):
        s = Settings(app_env="production")
        assert s.cors_allow_methods == ["GET", "POST", "PATCH", "DELETE", "OPTIONS"]

    def test_development_methods_wildcard(self):
        s = Settings(app_env="development")
        assert s.cors_allow_methods == ["*"]

    def test_production_headers_restricted(self):
        s = Settings(app_env="production")
        assert "Content-Type" in s.cors_allow_headers
        assert "X-API-Key" in s.cors_allow_headers
        assert "Authorization" in s.cors_allow_headers

    def test_development_headers_wildcard(self):
        s = Settings(app_env="development")
        assert s.cors_allow_headers == ["*"]
