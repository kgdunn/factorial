"""Tests for the experiments CRUD endpoints.

Uses FastAPI dependency overrides with a mock DB session to test
endpoint routing, schema validation, and response structure without
requiring a running PostgreSQL instance.
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime
from typing import Any
from unittest.mock import AsyncMock, patch

import pytest
from httpx import ASGITransport, AsyncClient

from app.main import app

# ---------------------------------------------------------------------------
# Mock experiment data
# ---------------------------------------------------------------------------

_NOW = datetime.now(UTC)

_SAMPLE_DESIGN_DATA: dict[str, Any] = {
    "design_type": "full_factorial",
    "n_factors": 2,
    "n_runs": 7,
    "factor_names": ["Temperature", "Pressure"],
    "design_coded": [
        {"Temperature": -1, "Pressure": -1},
        {"Temperature": 1, "Pressure": -1},
        {"Temperature": -1, "Pressure": 1},
        {"Temperature": 1, "Pressure": 1},
    ],
    "design_actual": [
        {"Temperature": 150, "Pressure": 1},
        {"Temperature": 200, "Pressure": 1},
        {"Temperature": 150, "Pressure": 5},
        {"Temperature": 200, "Pressure": 5},
    ],
    "run_order": [1, 2, 3, 4],
}

_SAMPLE_EXPERIMENT_ID = uuid.uuid4()


class _FakeExperiment:
    """Mimics an Experiment ORM object for testing."""

    def __init__(self, **kwargs: Any) -> None:
        self.id = kwargs.get("id", _SAMPLE_EXPERIMENT_ID)
        self.name = kwargs.get("name", "Full Factorial (2 factors, 7 runs)")
        self.status = kwargs.get("status", "draft")
        self.design_type = kwargs.get("design_type", "full_factorial")
        self.factors = kwargs.get("factors", [{"name": "Temperature"}, {"name": "Pressure"}])
        self.design_data = kwargs.get("design_data", _SAMPLE_DESIGN_DATA)
        self.results_data = kwargs.get("results_data")
        self.evaluation_data = kwargs.get("evaluation_data")
        self.conversation_id = kwargs.get("conversation_id")
        self.created_at = kwargs.get("created_at", _NOW)
        self.updated_at = kwargs.get("updated_at", _NOW)


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------


class TestListExperiments:
    """GET /api/v1/experiments"""

    @pytest.mark.asyncio
    async def test_list_empty(self):
        with patch("app.api.v1.endpoints.experiments.experiment_service") as mock_svc:
            mock_svc.list_experiments = AsyncMock(return_value=([], 0))

            transport = ASGITransport(app=app)
            async with AsyncClient(transport=transport, base_url="http://test") as ac:
                resp = await ac.get("/api/v1/experiments")

            assert resp.status_code == 200
            data = resp.json()
            assert data["experiments"] == []
            assert data["total"] == 0
            assert data["page"] == 1

    @pytest.mark.asyncio
    async def test_list_with_results(self):
        fake = _FakeExperiment()
        with patch("app.api.v1.endpoints.experiments.experiment_service") as mock_svc:
            mock_svc.list_experiments = AsyncMock(return_value=([fake], 1))

            transport = ASGITransport(app=app)
            async with AsyncClient(transport=transport, base_url="http://test") as ac:
                resp = await ac.get("/api/v1/experiments")

            assert resp.status_code == 200
            data = resp.json()
            assert len(data["experiments"]) == 1
            assert data["experiments"][0]["name"] == fake.name
            assert data["experiments"][0]["n_runs"] == 7
            assert data["experiments"][0]["n_factors"] == 2
            assert data["total"] == 1

    @pytest.mark.asyncio
    async def test_list_with_status_filter(self):
        with patch("app.api.v1.endpoints.experiments.experiment_service") as mock_svc:
            mock_svc.list_experiments = AsyncMock(return_value=([], 0))

            transport = ASGITransport(app=app)
            async with AsyncClient(transport=transport, base_url="http://test") as ac:
                resp = await ac.get("/api/v1/experiments?status=active")

            assert resp.status_code == 200
            mock_svc.list_experiments.assert_called_once()
            call_kwargs = mock_svc.list_experiments.call_args
            assert call_kwargs[1].get("status") == "active" or call_kwargs[0][1] == "active"

    @pytest.mark.asyncio
    async def test_list_pagination(self):
        with patch("app.api.v1.endpoints.experiments.experiment_service") as mock_svc:
            mock_svc.list_experiments = AsyncMock(return_value=([], 0))

            transport = ASGITransport(app=app)
            async with AsyncClient(transport=transport, base_url="http://test") as ac:
                resp = await ac.get("/api/v1/experiments?page=2&page_size=5")

            assert resp.status_code == 200
            data = resp.json()
            assert data["page"] == 2
            assert data["page_size"] == 5


class TestGetExperiment:
    """GET /api/v1/experiments/{id}"""

    @pytest.mark.asyncio
    async def test_get_existing(self):
        fake = _FakeExperiment()
        with patch("app.api.v1.endpoints.experiments.experiment_service") as mock_svc:
            mock_svc.get_experiment = AsyncMock(return_value=fake)

            transport = ASGITransport(app=app)
            async with AsyncClient(transport=transport, base_url="http://test") as ac:
                resp = await ac.get(f"/api/v1/experiments/{fake.id}")

            assert resp.status_code == 200
            data = resp.json()
            assert data["name"] == fake.name
            assert data["design_data"] is not None
            assert data["design_data"]["design_type"] == "full_factorial"

    @pytest.mark.asyncio
    async def test_get_not_found(self):
        with patch("app.api.v1.endpoints.experiments.experiment_service") as mock_svc:
            mock_svc.get_experiment = AsyncMock(return_value=None)

            transport = ASGITransport(app=app)
            async with AsyncClient(transport=transport, base_url="http://test") as ac:
                resp = await ac.get(f"/api/v1/experiments/{uuid.uuid4()}")

            assert resp.status_code == 404


class TestUpdateExperiment:
    """PATCH /api/v1/experiments/{id}"""

    @pytest.mark.asyncio
    async def test_update_name(self):
        fake = _FakeExperiment(name="Updated Name")
        with patch("app.api.v1.endpoints.experiments.experiment_service") as mock_svc:
            mock_svc.update_experiment = AsyncMock(return_value=fake)

            transport = ASGITransport(app=app)
            async with AsyncClient(transport=transport, base_url="http://test") as ac:
                resp = await ac.patch(
                    f"/api/v1/experiments/{fake.id}",
                    json={"name": "Updated Name"},
                )

            assert resp.status_code == 200
            assert resp.json()["name"] == "Updated Name"

    @pytest.mark.asyncio
    async def test_update_status(self):
        fake = _FakeExperiment(status="active")
        with patch("app.api.v1.endpoints.experiments.experiment_service") as mock_svc:
            mock_svc.update_experiment = AsyncMock(return_value=fake)

            transport = ASGITransport(app=app)
            async with AsyncClient(transport=transport, base_url="http://test") as ac:
                resp = await ac.patch(
                    f"/api/v1/experiments/{fake.id}",
                    json={"status": "active"},
                )

            assert resp.status_code == 200
            assert resp.json()["status"] == "active"

    @pytest.mark.asyncio
    async def test_update_not_found(self):
        with patch("app.api.v1.endpoints.experiments.experiment_service") as mock_svc:
            mock_svc.update_experiment = AsyncMock(return_value=None)

            transport = ASGITransport(app=app)
            async with AsyncClient(transport=transport, base_url="http://test") as ac:
                resp = await ac.patch(
                    f"/api/v1/experiments/{uuid.uuid4()}",
                    json={"name": "x"},
                )

            assert resp.status_code == 404

    @pytest.mark.asyncio
    async def test_update_empty_body_returns_400(self):
        with patch("app.api.v1.endpoints.experiments.experiment_service") as mock_svc:
            mock_svc.update_experiment = AsyncMock()

            transport = ASGITransport(app=app)
            async with AsyncClient(transport=transport, base_url="http://test") as ac:
                resp = await ac.patch(
                    f"/api/v1/experiments/{uuid.uuid4()}",
                    json={},
                )

            assert resp.status_code == 400


class TestDeleteExperiment:
    """DELETE /api/v1/experiments/{id}"""

    @pytest.mark.asyncio
    async def test_delete_existing(self):
        with patch("app.api.v1.endpoints.experiments.experiment_service") as mock_svc:
            mock_svc.delete_experiment = AsyncMock(return_value=True)

            transport = ASGITransport(app=app)
            async with AsyncClient(transport=transport, base_url="http://test") as ac:
                resp = await ac.delete(f"/api/v1/experiments/{uuid.uuid4()}")

            assert resp.status_code == 200
            assert resp.json()["detail"] == "Deleted"

    @pytest.mark.asyncio
    async def test_delete_not_found(self):
        with patch("app.api.v1.endpoints.experiments.experiment_service") as mock_svc:
            mock_svc.delete_experiment = AsyncMock(return_value=False)

            transport = ASGITransport(app=app)
            async with AsyncClient(transport=transport, base_url="http://test") as ac:
                resp = await ac.delete(f"/api/v1/experiments/{uuid.uuid4()}")

            assert resp.status_code == 404


class TestResults:
    """POST/GET /api/v1/experiments/{id}/results"""

    @pytest.mark.asyncio
    async def test_add_results(self):
        fake = _FakeExperiment(results_data=[{"run_index": 0, "yield": 85.2}])
        with patch("app.api.v1.endpoints.experiments.experiment_service") as mock_svc:
            mock_svc.add_results = AsyncMock(return_value=fake)

            transport = ASGITransport(app=app)
            async with AsyncClient(transport=transport, base_url="http://test") as ac:
                resp = await ac.post(
                    f"/api/v1/experiments/{fake.id}/results",
                    json={"results": [{"run_index": 0, "yield": 85.2}]},
                )

            assert resp.status_code == 200
            data = resp.json()
            assert data["n_results_entered"] == 1

    @pytest.mark.asyncio
    async def test_add_results_not_found(self):
        with patch("app.api.v1.endpoints.experiments.experiment_service") as mock_svc:
            mock_svc.add_results = AsyncMock(return_value=None)

            transport = ASGITransport(app=app)
            async with AsyncClient(transport=transport, base_url="http://test") as ac:
                resp = await ac.post(
                    f"/api/v1/experiments/{uuid.uuid4()}/results",
                    json={"results": [{"run_index": 0, "yield": 1.0}]},
                )

            assert resp.status_code == 404

    @pytest.mark.asyncio
    async def test_add_results_empty_list_returns_422(self):
        """Empty results list should fail Pydantic validation."""
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as ac:
            resp = await ac.post(
                f"/api/v1/experiments/{uuid.uuid4()}/results",
                json={"results": []},
            )

        assert resp.status_code == 422

    @pytest.mark.asyncio
    async def test_get_results(self):
        results_data = [{"run_index": 0, "yield": 85.2}, {"run_index": 1, "yield": 91.0}]
        with patch("app.api.v1.endpoints.experiments.experiment_service") as mock_svc:
            mock_svc.get_results = AsyncMock(return_value=(results_data, 2))

            transport = ASGITransport(app=app)
            async with AsyncClient(transport=transport, base_url="http://test") as ac:
                resp = await ac.get(f"/api/v1/experiments/{uuid.uuid4()}/results")

            assert resp.status_code == 200
            data = resp.json()
            assert data["n_results_entered"] == 2
            assert len(data["results_data"]) == 2

    @pytest.mark.asyncio
    async def test_get_results_not_found(self):
        with patch("app.api.v1.endpoints.experiments.experiment_service") as mock_svc:
            mock_svc.get_results = AsyncMock(return_value=(None, 0))

            transport = ASGITransport(app=app)
            async with AsyncClient(transport=transport, base_url="http://test") as ac:
                resp = await ac.get(f"/api/v1/experiments/{uuid.uuid4()}/results")

            assert resp.status_code == 404
