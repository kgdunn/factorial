"""Tests for the owner-scoped share-link + export endpoints.

Mocks the services layer and asserts routing, response shape, and the
``acknowledge_share`` gate on PDF exports.
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
        self.token = overrides.get("token", "tok_abc123")
        self.experiment_id = overrides.get("experiment_id", uuid.uuid4())
        self.allow_results = overrides.get("allow_results", True)
        self.expires_at = overrides.get("expires_at", datetime.now(UTC) + timedelta(days=30))
        self.revoked_at = overrides.get("revoked_at")
        self.view_count = overrides.get("view_count", 0)
        self.created_at = overrides.get("created_at", datetime.now(UTC))


class _FakeExperiment:
    def __init__(self) -> None:
        self.id = uuid.uuid4()
        self.name = "Sample"
        self.status = "active"
        self.design_type = "full_factorial"
        self.factors = []
        self.design_data = {"n_factors": 2, "n_runs": 4, "design_actual": []}
        self.results_data = []
        self.created_at = datetime.now(UTC)
        self.user_id = None


@pytest.mark.asyncio
class TestCreateShareLink:
    async def test_create_success(self):
        share = _FakeShare()
        with patch("app.api.v1.endpoints.experiments.share_service") as mock_svc:
            mock_svc.create_share = AsyncMock(return_value=share)
            mock_svc.build_share_response_dict = lambda s: {
                "id": s.id,
                "token": s.token,
                "url": f"http://test/share/{s.token}",
                "allow_results": s.allow_results,
                "expires_at": s.expires_at,
                "revoked_at": s.revoked_at,
                "view_count": s.view_count,
                "created_at": s.created_at,
            }
            transport = ASGITransport(app=app)
            async with AsyncClient(transport=transport, base_url="http://test") as ac:
                resp = await ac.post(
                    f"/api/v1/experiments/{uuid.uuid4()}/shares",
                    json={"allow_results": True, "never_expire": False},
                )
        assert resp.status_code == 200
        data = resp.json()
        assert data["token"] == share.token
        assert data["view_count"] == 0

    async def test_create_experiment_missing_returns_404(self):
        with patch("app.api.v1.endpoints.experiments.share_service") as mock_svc:
            mock_svc.create_share = AsyncMock(return_value=None)
            transport = ASGITransport(app=app)
            async with AsyncClient(transport=transport, base_url="http://test") as ac:
                resp = await ac.post(
                    f"/api/v1/experiments/{uuid.uuid4()}/shares",
                    json={},
                )
        assert resp.status_code == 404


@pytest.mark.asyncio
class TestListShareLinks:
    async def test_list_returns_shares(self):
        share = _FakeShare()
        with patch("app.api.v1.endpoints.experiments.share_service") as mock_svc:
            mock_svc.list_shares = AsyncMock(return_value=[share])
            mock_svc.build_share_response_dict = lambda s: {
                "id": s.id,
                "token": s.token,
                "url": f"http://test/share/{s.token}",
                "allow_results": s.allow_results,
                "expires_at": s.expires_at,
                "revoked_at": s.revoked_at,
                "view_count": s.view_count,
                "created_at": s.created_at,
            }
            transport = ASGITransport(app=app)
            async with AsyncClient(transport=transport, base_url="http://test") as ac:
                resp = await ac.get(f"/api/v1/experiments/{uuid.uuid4()}/shares")
        assert resp.status_code == 200
        assert len(resp.json()["shares"]) == 1


@pytest.mark.asyncio
class TestRevokeShareLink:
    async def test_revoke_success(self):
        with patch("app.api.v1.endpoints.experiments.share_service") as mock_svc:
            mock_svc.revoke_share = AsyncMock(return_value=True)
            transport = ASGITransport(app=app)
            async with AsyncClient(transport=transport, base_url="http://test") as ac:
                resp = await ac.delete("/api/v1/experiments/shares/tok_abc")
        assert resp.status_code == 200
        assert resp.json()["detail"] == "Revoked"

    async def test_revoke_not_found(self):
        with patch("app.api.v1.endpoints.experiments.share_service") as mock_svc:
            mock_svc.revoke_share = AsyncMock(return_value=False)
            transport = ASGITransport(app=app)
            async with AsyncClient(transport=transport, base_url="http://test") as ac:
                resp = await ac.delete("/api/v1/experiments/shares/unknown")
        assert resp.status_code == 404


@pytest.mark.asyncio
class TestExportEndpoint:
    async def test_csv_export(self):
        exp = _FakeExperiment()
        with patch("app.api.v1.endpoints.experiments.experiment_service") as mock_svc:
            mock_svc.get_experiment = AsyncMock(return_value=exp)
            transport = ASGITransport(app=app)
            async with AsyncClient(transport=transport, base_url="http://test") as ac:
                resp = await ac.get(f"/api/v1/experiments/{exp.id}/export?format=csv")
        assert resp.status_code == 200
        assert resp.headers["content-type"].startswith("text/csv")
        assert "attachment" in resp.headers["content-disposition"]
        assert resp.headers["content-disposition"].endswith('.csv"')

    async def test_pdf_export_requires_acknowledgement(self):
        exp = _FakeExperiment()
        with patch("app.api.v1.endpoints.experiments.experiment_service") as mock_svc:
            mock_svc.get_experiment = AsyncMock(return_value=exp)
            transport = ASGITransport(app=app)
            async with AsyncClient(transport=transport, base_url="http://test") as ac:
                resp = await ac.get(f"/api/v1/experiments/{exp.id}/export?format=pdf")
        assert resp.status_code == 400

    async def test_pdf_export_not_found(self):
        with patch("app.api.v1.endpoints.experiments.experiment_service") as mock_svc:
            mock_svc.get_experiment = AsyncMock(return_value=None)
            transport = ASGITransport(app=app)
            async with AsyncClient(transport=transport, base_url="http://test") as ac:
                resp = await ac.get(f"/api/v1/experiments/{uuid.uuid4()}/export?format=csv")
        assert resp.status_code == 404

    async def test_xlsx_export(self):
        exp = _FakeExperiment()
        with patch("app.api.v1.endpoints.experiments.experiment_service") as mock_svc:
            mock_svc.get_experiment = AsyncMock(return_value=exp)
            transport = ASGITransport(app=app)
            async with AsyncClient(transport=transport, base_url="http://test") as ac:
                resp = await ac.get(f"/api/v1/experiments/{exp.id}/export?format=xlsx")
        assert resp.status_code == 200
        assert "spreadsheetml" in resp.headers["content-type"]

    async def test_md_export(self):
        exp = _FakeExperiment()
        with patch("app.api.v1.endpoints.experiments.experiment_service") as mock_svc:
            mock_svc.get_experiment = AsyncMock(return_value=exp)
            transport = ASGITransport(app=app)
            async with AsyncClient(transport=transport, base_url="http://test") as ac:
                resp = await ac.get(f"/api/v1/experiments/{exp.id}/export?format=md")
        assert resp.status_code == 200
        assert resp.headers["content-type"].startswith("text/markdown")
