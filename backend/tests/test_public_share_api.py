"""Tests for the unauthenticated ``/api/v1/public/experiments/{token}`` endpoint.

Mocks ``share_service.resolve_public_share`` to avoid the database.
Confirms that ``allow_results=False`` hides run-level data, that
view_count is echoed back, and that revoked / unknown tokens return 404.
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime, timedelta
from typing import Any
from unittest.mock import AsyncMock, patch

import pytest
from httpx import ASGITransport, AsyncClient

from app.main import app


class _FakeShare:
    def __init__(self, **overrides: Any) -> None:
        self.id = overrides.get("id", uuid.uuid4())
        self.token = overrides.get("token", "tok_xyz")
        self.experiment_id = overrides.get("experiment_id", uuid.uuid4())
        self.allow_results = overrides.get("allow_results", True)
        self.expires_at = overrides.get("expires_at", datetime.now(UTC) + timedelta(days=30))
        self.revoked_at = overrides.get("revoked_at")
        self.view_count = overrides.get("view_count", 7)
        self.created_at = overrides.get("created_at", datetime.now(UTC))


class _FakeExperiment:
    def __init__(self, **overrides: Any) -> None:
        self.id = overrides.get("id", uuid.uuid4())
        self.name = "Public Sample"
        self.status = "active"
        self.design_type = "full_factorial"
        self.factors = [{"name": "A"}, {"name": "B"}]
        self.design_data = {
            "n_factors": 2,
            "n_runs": 4,
            "design_actual": [
                {"A": 1, "B": 1},
                {"A": 2, "B": 2},
            ],
        }
        self.results_data = [{"run_index": 0, "yield": 90}]
        self.created_at = datetime.now(UTC)
        self.user_id = None


@pytest.mark.asyncio
class TestPublicGet:
    async def test_happy_path_returns_view_count(self):
        share = _FakeShare(view_count=42)
        exp = _FakeExperiment()
        with patch("app.api.v1.endpoints.shares_public.share_service") as mock_svc:
            mock_svc.resolve_public_share = AsyncMock(return_value=(share, exp))
            transport = ASGITransport(app=app)
            async with AsyncClient(transport=transport, base_url="http://test") as ac:
                resp = await ac.get(f"/api/v1/public/experiments/{share.token}")
        assert resp.status_code == 200
        data = resp.json()
        assert data["name"] == "Public Sample"
        assert data["view_count"] == 42
        assert data["token"] == share.token
        assert data["results_data"] is not None
        # Owner PII must never leak through the public endpoint.
        assert "user_id" not in data
        assert "conversation_id" not in data

    async def test_allow_results_false_hides_responses(self):
        share = _FakeShare(allow_results=False)
        exp = _FakeExperiment()
        with patch("app.api.v1.endpoints.shares_public.share_service") as mock_svc:
            mock_svc.resolve_public_share = AsyncMock(return_value=(share, exp))
            transport = ASGITransport(app=app)
            async with AsyncClient(transport=transport, base_url="http://test") as ac:
                resp = await ac.get(f"/api/v1/public/experiments/{share.token}")
        assert resp.status_code == 200
        data = resp.json()
        assert data["results_data"] is None
        assert data["allow_results"] is False

    async def test_unknown_or_revoked_returns_404(self):
        with patch("app.api.v1.endpoints.shares_public.share_service") as mock_svc:
            mock_svc.resolve_public_share = AsyncMock(return_value=None)
            transport = ASGITransport(app=app)
            async with AsyncClient(transport=transport, base_url="http://test") as ac:
                resp = await ac.get("/api/v1/public/experiments/revoked-tok")
        assert resp.status_code == 404


@pytest.mark.asyncio
class TestPublicExport:
    async def test_csv_download_works(self):
        share = _FakeShare()
        exp = _FakeExperiment()
        with patch("app.api.v1.endpoints.shares_public.share_service") as mock_svc:
            mock_svc.resolve_public_share = AsyncMock(return_value=(share, exp))
            transport = ASGITransport(app=app)
            async with AsyncClient(transport=transport, base_url="http://test") as ac:
                resp = await ac.get(f"/api/v1/public/experiments/{share.token}/export?format=csv")
        assert resp.status_code == 200
        assert resp.headers["content-type"].startswith("text/csv")

    async def test_csv_blocked_when_results_disabled(self):
        share = _FakeShare(allow_results=False)
        exp = _FakeExperiment()
        with patch("app.api.v1.endpoints.shares_public.share_service") as mock_svc:
            mock_svc.resolve_public_share = AsyncMock(return_value=(share, exp))
            transport = ASGITransport(app=app)
            async with AsyncClient(transport=transport, base_url="http://test") as ac:
                resp = await ac.get(f"/api/v1/public/experiments/{share.token}/export?format=csv")
        assert resp.status_code == 403
