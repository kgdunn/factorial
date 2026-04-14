import os

import pytest
from httpx import ASGITransport, AsyncClient

# Set testing environment before importing the app
os.environ["APP_ENV"] = "testing"

from app.main import app  # noqa: E402


@pytest.fixture
async def client():
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        yield ac
