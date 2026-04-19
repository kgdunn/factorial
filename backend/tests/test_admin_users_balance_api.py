"""HTTP-level tests for ``POST /api/v1/admin/users/{id}/balance/topup``."""

from __future__ import annotations

import uuid
from decimal import Decimal
from unittest.mock import AsyncMock, patch

import pytest
from httpx import AsyncClient

from app.api.deps import TESTING_USER_ID, AuthUser, require_auth
from app.main import app


class _FakeUser:
    def __init__(self, uid: uuid.UUID, email: str = "target@example.com") -> None:
        self.id = uid
        self.email = email


class _FakeBalance:
    def __init__(self, uid: uuid.UUID, usd: Decimal, tokens: int) -> None:
        self.user_id = uid
        self.balance_usd = usd
        self.balance_tokens = tokens


@pytest.mark.asyncio
async def test_top_up_credits_balance(client: AsyncClient) -> None:
    target_id = uuid.uuid4()
    with (
        patch("app.services.auth_service.get_user_by_id", new=AsyncMock(return_value=_FakeUser(target_id))),
        patch("app.api.v1.endpoints.admin_users.balance_service") as bal,
    ):
        bal.top_up = AsyncMock(return_value=_FakeBalance(target_id, Decimal("15.2500"), 2_500_000))
        resp = await client.post(
            f"/api/v1/admin/users/{target_id}/balance/topup",
            json={"usd": "15.25", "tokens": 2_500_000},
        )

    assert resp.status_code == 200
    body = resp.json()
    assert body["user_id"] == str(target_id)
    assert Decimal(body["balance_usd"]) == Decimal("15.2500")
    assert body["balance_tokens"] == 2_500_000

    kwargs = bal.top_up.call_args.kwargs
    assert kwargs["user_id"] == target_id
    assert kwargs["usd"] == Decimal("15.25")
    assert kwargs["tokens"] == 2_500_000


@pytest.mark.asyncio
async def test_top_up_rejects_zero_amounts(client: AsyncClient) -> None:
    resp = await client.post(
        f"/api/v1/admin/users/{uuid.uuid4()}/balance/topup",
        json={"usd": "0", "tokens": 0},
    )
    assert resp.status_code == 422


@pytest.mark.asyncio
async def test_top_up_missing_user_returns_404(client: AsyncClient) -> None:
    with patch("app.services.auth_service.get_user_by_id", new=AsyncMock(return_value=None)):
        resp = await client.post(
            f"/api/v1/admin/users/{uuid.uuid4()}/balance/topup",
            json={"usd": "1.00", "tokens": 0},
        )
    assert resp.status_code == 404


@pytest.mark.asyncio
async def test_top_up_rejects_non_admin(client: AsyncClient) -> None:
    async def _non_admin() -> AuthUser:
        return AuthUser(id=TESTING_USER_ID, email="plain@example.com", display_name=None, is_admin=False)

    original = app.dependency_overrides.get(require_auth)
    app.dependency_overrides[require_auth] = _non_admin
    try:
        resp = await client.post(
            f"/api/v1/admin/users/{uuid.uuid4()}/balance/topup",
            json={"usd": "1.00", "tokens": 0},
        )
        assert resp.status_code == 403
    finally:
        if original is not None:
            app.dependency_overrides[require_auth] = original
        else:
            app.dependency_overrides.pop(require_auth, None)
