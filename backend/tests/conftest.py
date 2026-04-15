import os

import pytest
from httpx import ASGITransport, AsyncClient

# Set testing environment before importing the app
os.environ["APP_ENV"] = "testing"

from app.api.deps import TESTING_USER_ID, AuthUser, require_api_key, require_auth  # noqa: E402
from app.main import app  # noqa: E402

# ---------------------------------------------------------------------------
# Auth overrides for testing — replaces the old APP_ENV=testing bypass
# that lived in production code.
# ---------------------------------------------------------------------------


def _testing_user() -> AuthUser:
    """Synthetic user returned by auth dependencies during tests."""
    return AuthUser(
        id=TESTING_USER_ID,
        email="test@example.com",
        display_name="Test User",
        is_service_account=True,
    )


async def _auth_override() -> AuthUser:
    return _testing_user()


async def _api_key_override() -> str:
    return "testing-bypass"


# Apply overrides so every test client skips real authentication.
app.dependency_overrides[require_auth] = _auth_override
app.dependency_overrides[require_api_key] = _api_key_override


@pytest.fixture
async def client():
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        yield ac
