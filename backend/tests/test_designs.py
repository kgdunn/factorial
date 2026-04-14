"""Integration tests for the designs endpoint."""

import pytest

_SKIP_REASON = "process-improve not yet available in deployment"


@pytest.mark.skip(reason=_SKIP_REASON)
@pytest.mark.asyncio
async def test_generate_full_factorial(client):
    """Generate a 2^2 full factorial and verify structure."""
    payload = {
        "factors": [
            {"name": "Temperature", "low": 150.0, "high": 200.0, "units": "degC"},
            {"name": "Pressure", "low": 1.0, "high": 5.0, "units": "bar"},
        ],
        "design_type": "full_factorial",
    }
    response = await client.post("/api/v1/designs/generate", json=payload)
    assert response.status_code == 200

    data = response.json()
    assert data["design_type"] == "full_factorial"
    assert data["n_factors"] == 2
    assert data["n_runs"] >= 4  # 2^2 = 4, may include center points
    assert set(data["factor_names"]) == {"Temperature", "Pressure"}
    assert len(data["design_coded"]) == data["n_runs"]
    assert len(data["design_actual"]) == data["n_runs"]
    assert len(data["run_order"]) == data["n_runs"]


@pytest.mark.skip(reason=_SKIP_REASON)
@pytest.mark.asyncio
async def test_generate_ccd(client):
    """Generate a CCD with 3 factors."""
    payload = {
        "factors": [
            {"name": "A", "low": -1.0, "high": 1.0},
            {"name": "B", "low": -1.0, "high": 1.0},
            {"name": "C", "low": -1.0, "high": 1.0},
        ],
        "design_type": "ccd",
        "alpha": "rotatable",
    }
    response = await client.post("/api/v1/designs/generate", json=payload)
    assert response.status_code == 200

    data = response.json()
    assert data["design_type"] == "ccd"
    assert data["n_factors"] == 3
    assert data["alpha"] is not None


@pytest.mark.skip(reason=_SKIP_REASON)
@pytest.mark.asyncio
async def test_generate_design_auto_selects_type(client):
    """When design_type is omitted, auto-selection kicks in."""
    payload = {
        "factors": [
            {"name": "X1", "low": 0.0, "high": 10.0},
            {"name": "X2", "low": 0.0, "high": 10.0},
        ],
    }
    response = await client.post("/api/v1/designs/generate", json=payload)
    assert response.status_code == 200
    data = response.json()
    assert data["design_type"]  # some type was selected
    assert data["n_runs"] > 0


@pytest.mark.asyncio
async def test_generate_design_validation_error(client):
    """Missing required factor fields should return 422."""
    payload = {
        "factors": [
            {"name": "Temperature"},  # missing low/high for continuous
        ],
    }
    response = await client.post("/api/v1/designs/generate", json=payload)
    assert response.status_code == 422


@pytest.mark.asyncio
async def test_generate_design_empty_factors(client):
    """Empty factors list should return 422."""
    payload = {"factors": []}
    response = await client.post("/api/v1/designs/generate", json=payload)
    assert response.status_code == 422


@pytest.mark.asyncio
async def test_tool_error_returns_422(client):
    """When process-improve returns an error, it should be HTTP 422."""
    payload = {
        "factors": [
            {"name": "A", "low": 0.0, "high": 1.0},
        ],
        "design_type": "box_behnken",  # Box-Behnken needs >= 3 factors
    }
    response = await client.post("/api/v1/designs/generate", json=payload)
    assert response.status_code == 422
    data = response.json()
    assert "error" in data
