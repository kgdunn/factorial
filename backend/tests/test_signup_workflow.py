"""End-to-end tests for the invite-based signup workflow.

Covers the three public/admin transitions:

    POST /signup/request          (applicant submits)
    POST /signup/admin/{id}/approve  OR  /reject  (admin moderates)
    POST /signup/invite/register  (applicant completes account)

The tests share the per-test ``db_session`` with the FastAPI route handlers
by overriding ``get_db_session`` so HTTP writes and direct queries see the
same SAVEPOINT-wrapped state, then everything rolls back at teardown.

The regression that motivated this file: ``register_with_invite`` 500'd
with ``MissingGreenlet`` because the freshly-flushed ``User`` had no
``role`` relationship loaded, and serialising ``user.role.name`` in
``UserResponse.background`` triggered an async lazy-load. Test
``TestCompleteRegistration::test_full_workflow_returns_role_name_in_background``
is the assertion that would have caught it.
"""

from __future__ import annotations

import uuid
from collections.abc import AsyncGenerator
from contextlib import asynccontextmanager

import pytest
from httpx import AsyncClient
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import TESTING_USER_ID, AuthUser, require_auth
from app.api.rate_limit import limiter
from app.db.session import get_db_session
from app.main import app
from app.models.role import Role
from app.models.signup_request import SignupRequest
from app.models.user import User
from app.models.user_balance import UserBalance
from app.services import role_service
from app.services.auth_service import hash_password

# ---------------------------------------------------------------------------
# Fixtures local to this module
# ---------------------------------------------------------------------------


@pytest.fixture(autouse=True)
def _disable_rate_limiter() -> AsyncGenerator[None, None]:
    """Disable slowapi for the workflow tests.

    ``register_rate_limit`` defaults to ``3/hour`` and ``signup/request`` is
    decorated with it. The in-memory limiter persists across tests in the
    same process, so a fixture that runs three submissions exhausts the
    quota for every later test. We're not testing the limiter here.
    """
    original = limiter.enabled
    limiter.enabled = False
    try:
        yield
    finally:
        limiter.enabled = original


@pytest.fixture
async def db_client(client: AsyncClient, db_session: AsyncSession) -> AsyncGenerator[AsyncClient, None]:
    """``AsyncClient`` whose route handlers receive the per-test session.

    Without this override each HTTP request would open its own connection
    against the production engine and writes would not be visible to
    ``db_session`` queries (and vice versa).
    """

    async def _override() -> AsyncGenerator[AsyncSession, None]:
        yield db_session

    app.dependency_overrides[get_db_session] = _override
    try:
        yield client
    finally:
        app.dependency_overrides.pop(get_db_session, None)


@asynccontextmanager
async def _auth_as(*, is_admin: bool) -> AsyncGenerator[None, None]:
    """Temporarily swap ``require_auth`` for a synthetic user with the given admin flag."""

    async def _override() -> AuthUser:
        return AuthUser(
            id=TESTING_USER_ID,
            email="non-admin@example.com" if not is_admin else "admin@example.com",
            display_name="Test User",
            is_admin=is_admin,
        )

    original = app.dependency_overrides.get(require_auth)
    app.dependency_overrides[require_auth] = _override
    try:
        yield
    finally:
        if original is not None:
            app.dependency_overrides[require_auth] = original
        else:
            app.dependency_overrides.pop(require_auth, None)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _signup_payload(**overrides: object) -> dict[str, object]:
    payload: dict[str, object] = {
        "email": "applicant@example.com",
        "use_case": "I want to run factorial designs on our reactor.",
        "requested_role": "chemical_engineer",
        "accepted_disclaimers": True,
    }
    payload.update(overrides)
    return payload


async def _fetch_signup_by_email(db: AsyncSession, email: str) -> SignupRequest:
    result = await db.execute(select(SignupRequest).where(SignupRequest.email == email))
    return result.scalar_one()


async def _chemical_engineer_role(db: AsyncSession) -> Role:
    role = await role_service.get_role_by_name(db, "chemical_engineer")
    assert role is not None, "built-in role 'chemical_engineer' should be seeded by alembic"
    return role


# ---------------------------------------------------------------------------
# Public submission
# ---------------------------------------------------------------------------


class TestSignupRequest:
    @pytest.mark.asyncio
    async def test_submit_creates_pending_signup(self, db_client: AsyncClient, db_session: AsyncSession) -> None:
        resp = await db_client.post("/api/v1/signup/request", json=_signup_payload())

        assert resp.status_code == 201
        signup = await _fetch_signup_by_email(db_session, "applicant@example.com")
        assert signup.status == "pending"
        assert signup.accepted_disclaimers is True
        assert signup.disclaimers_accepted_at is not None
        assert signup.requested_role == "chemical_engineer"
        assert signup.invite_token is None
        assert signup.role_id is None

    @pytest.mark.asyncio
    async def test_submit_rejects_duplicate_email(self, db_client: AsyncClient) -> None:
        first = await db_client.post("/api/v1/signup/request", json=_signup_payload())
        assert first.status_code == 201

        second = await db_client.post("/api/v1/signup/request", json=_signup_payload())
        assert second.status_code == 409

    @pytest.mark.asyncio
    async def test_submit_requires_disclaimers(self, db_client: AsyncClient) -> None:
        resp = await db_client.post(
            "/api/v1/signup/request",
            json=_signup_payload(accepted_disclaimers=False),
        )
        assert resp.status_code == 422


# ---------------------------------------------------------------------------
# Admin approve / reject
# ---------------------------------------------------------------------------


class TestAdminApproveReject:
    @pytest.mark.asyncio
    async def test_approve_with_existing_role_assigns_role_and_token(
        self, db_client: AsyncClient, db_session: AsyncSession
    ) -> None:
        await db_client.post("/api/v1/signup/request", json=_signup_payload())
        signup = await _fetch_signup_by_email(db_session, "applicant@example.com")
        role = await _chemical_engineer_role(db_session)

        resp = await db_client.post(
            f"/api/v1/signup/admin/{signup.id}/approve",
            json={"role_id": str(role.id)},
        )
        assert resp.status_code == 200

        await db_session.refresh(signup)
        assert signup.status == "approved"
        assert signup.invite_token
        assert signup.role_id == role.id
        assert signup.invite_expires_at is not None

    @pytest.mark.asyncio
    async def test_approve_with_new_role_creates_role(self, db_client: AsyncClient, db_session: AsyncSession) -> None:
        await db_client.post(
            "/api/v1/signup/request",
            json=_signup_payload(email="new-role-applicant@example.com"),
        )
        signup = await _fetch_signup_by_email(db_session, "new-role-applicant@example.com")

        resp = await db_client.post(
            f"/api/v1/signup/admin/{signup.id}/approve",
            json={"new_role": {"name": "Test Role", "description": "Custom role for tests"}},
        )
        assert resp.status_code == 200

        await db_session.refresh(signup)
        new_role = await role_service.get_role_by_name(db_session, "test_role")
        assert new_role is not None
        assert new_role.is_builtin is False
        assert signup.role_id == new_role.id

    @pytest.mark.asyncio
    async def test_approve_rejects_both_role_id_and_new_role(
        self, db_client: AsyncClient, db_session: AsyncSession
    ) -> None:
        await db_client.post("/api/v1/signup/request", json=_signup_payload())
        signup = await _fetch_signup_by_email(db_session, "applicant@example.com")
        role = await _chemical_engineer_role(db_session)

        resp = await db_client.post(
            f"/api/v1/signup/admin/{signup.id}/approve",
            json={
                "role_id": str(role.id),
                "new_role": {"name": "Other Role", "description": None},
            },
        )
        assert resp.status_code == 400

    @pytest.mark.asyncio
    async def test_approve_rejects_neither_role_id_nor_new_role(
        self, db_client: AsyncClient, db_session: AsyncSession
    ) -> None:
        await db_client.post("/api/v1/signup/request", json=_signup_payload())
        signup = await _fetch_signup_by_email(db_session, "applicant@example.com")

        resp = await db_client.post(
            f"/api/v1/signup/admin/{signup.id}/approve",
            json={},
        )
        assert resp.status_code == 400

    @pytest.mark.asyncio
    async def test_reject_marks_signup_rejected_with_note(
        self, db_client: AsyncClient, db_session: AsyncSession
    ) -> None:
        await db_client.post("/api/v1/signup/request", json=_signup_payload())
        signup = await _fetch_signup_by_email(db_session, "applicant@example.com")

        resp = await db_client.post(
            f"/api/v1/signup/admin/{signup.id}/reject",
            json={"note": "Use case is out of scope."},
        )
        assert resp.status_code == 200

        await db_session.refresh(signup)
        assert signup.status == "rejected"
        assert signup.admin_note == "Use case is out of scope."
        assert signup.invite_token is None

    @pytest.mark.asyncio
    async def test_reject_then_approve_fails(self, db_client: AsyncClient, db_session: AsyncSession) -> None:
        await db_client.post("/api/v1/signup/request", json=_signup_payload())
        signup = await _fetch_signup_by_email(db_session, "applicant@example.com")

        reject_resp = await db_client.post(f"/api/v1/signup/admin/{signup.id}/reject", json={})
        assert reject_resp.status_code == 200

        role = await _chemical_engineer_role(db_session)
        approve_resp = await db_client.post(
            f"/api/v1/signup/admin/{signup.id}/approve",
            json={"role_id": str(role.id)},
        )
        assert approve_resp.status_code == 400

    @pytest.mark.asyncio
    async def test_non_admin_cannot_approve(self, db_client: AsyncClient, db_session: AsyncSession) -> None:
        await db_client.post("/api/v1/signup/request", json=_signup_payload())
        signup = await _fetch_signup_by_email(db_session, "applicant@example.com")
        role = await _chemical_engineer_role(db_session)

        async with _auth_as(is_admin=False):
            resp = await db_client.post(
                f"/api/v1/signup/admin/{signup.id}/approve",
                json={"role_id": str(role.id)},
            )
        assert resp.status_code == 403

    @pytest.mark.asyncio
    async def test_non_admin_cannot_reject(self, db_client: AsyncClient, db_session: AsyncSession) -> None:
        await db_client.post("/api/v1/signup/request", json=_signup_payload())
        signup = await _fetch_signup_by_email(db_session, "applicant@example.com")

        async with _auth_as(is_admin=False):
            resp = await db_client.post(
                f"/api/v1/signup/admin/{signup.id}/reject",
                json={"note": "no"},
            )
        assert resp.status_code == 403


# ---------------------------------------------------------------------------
# Complete registration via invite — the regression-test target
# ---------------------------------------------------------------------------


class TestCompleteRegistration:
    @pytest.mark.asyncio
    async def test_full_workflow_returns_role_name_in_background(
        self, db_client: AsyncClient, db_session: AsyncSession
    ) -> None:
        """Submit -> approve -> register. Asserts ``background == role.name``.

        Without ``await db.refresh(user)`` in ``complete_registration``, this
        fails with ``sqlalchemy.exc.MissingGreenlet`` when the endpoint reads
        ``user.role.name`` for ``UserResponse.background``.
        """
        await db_client.post("/api/v1/signup/request", json=_signup_payload())
        signup = await _fetch_signup_by_email(db_session, "applicant@example.com")
        role = await _chemical_engineer_role(db_session)

        approve_resp = await db_client.post(
            f"/api/v1/signup/admin/{signup.id}/approve",
            json={"role_id": str(role.id)},
        )
        assert approve_resp.status_code == 200
        await db_session.refresh(signup)
        token = signup.invite_token
        assert token

        register_resp = await db_client.post(
            "/api/v1/signup/invite/register",
            json={"token": token, "password": "securepass123", "display_name": "Alice"},
        )
        assert register_resp.status_code == 201
        body = register_resp.json()
        assert body["email"] == "applicant@example.com"
        assert body["display_name"] == "Alice"
        assert body["background"] == "chemical_engineer"
        assert body["is_admin"] is False

    @pytest.mark.asyncio
    async def test_register_with_invalid_token_returns_400(self, db_client: AsyncClient) -> None:
        resp = await db_client.post(
            "/api/v1/signup/invite/register",
            json={"token": "this-token-does-not-exist", "password": "securepass123"},
        )
        assert resp.status_code == 400

    @pytest.mark.asyncio
    async def test_register_with_already_used_token_returns_400(
        self, db_client: AsyncClient, db_session: AsyncSession
    ) -> None:
        await db_client.post("/api/v1/signup/request", json=_signup_payload())
        signup = await _fetch_signup_by_email(db_session, "applicant@example.com")
        role = await _chemical_engineer_role(db_session)
        await db_client.post(
            f"/api/v1/signup/admin/{signup.id}/approve",
            json={"role_id": str(role.id)},
        )
        await db_session.refresh(signup)
        token = signup.invite_token
        assert token

        first = await db_client.post(
            "/api/v1/signup/invite/register",
            json={"token": token, "password": "securepass123", "display_name": "Alice"},
        )
        assert first.status_code == 201

        replay = await db_client.post(
            "/api/v1/signup/invite/register",
            json={"token": token, "password": "securepass123", "display_name": "Alice"},
        )
        assert replay.status_code == 400

    @pytest.mark.asyncio
    async def test_register_when_user_email_already_exists_returns_400(
        self, db_client: AsyncClient, db_session: AsyncSession
    ) -> None:
        await db_client.post("/api/v1/signup/request", json=_signup_payload())
        signup = await _fetch_signup_by_email(db_session, "applicant@example.com")
        role = await _chemical_engineer_role(db_session)
        await db_client.post(
            f"/api/v1/signup/admin/{signup.id}/approve",
            json={"role_id": str(role.id)},
        )
        await db_session.refresh(signup)
        token = signup.invite_token
        assert token

        existing = User(
            email="applicant@example.com",
            password_hash=hash_password("anything12345"),
            display_name="Pre-existing",
        )
        db_session.add(existing)
        await db_session.flush()

        resp = await db_client.post(
            "/api/v1/signup/invite/register",
            json={"token": token, "password": "securepass123", "display_name": "Alice"},
        )
        assert resp.status_code == 400

    @pytest.mark.asyncio
    async def test_register_marks_signup_as_registered_and_creates_balance(
        self, db_client: AsyncClient, db_session: AsyncSession
    ) -> None:
        await db_client.post("/api/v1/signup/request", json=_signup_payload())
        signup = await _fetch_signup_by_email(db_session, "applicant@example.com")
        role = await _chemical_engineer_role(db_session)
        await db_client.post(
            f"/api/v1/signup/admin/{signup.id}/approve",
            json={"role_id": str(role.id)},
        )
        await db_session.refresh(signup)
        token = signup.invite_token
        assert token

        resp = await db_client.post(
            "/api/v1/signup/invite/register",
            json={"token": token, "password": "securepass123", "display_name": "Alice"},
        )
        assert resp.status_code == 201
        user_id = uuid.UUID(resp.json()["id"])

        await db_session.refresh(signup)
        assert signup.status == "registered"

        balance_row = (await db_session.execute(select(UserBalance).where(UserBalance.user_id == user_id))).scalar_one()
        assert balance_row.user_id == user_id

    @pytest.mark.asyncio
    async def test_validate_invite_endpoint_does_not_consume_token(
        self, db_client: AsyncClient, db_session: AsyncSession
    ) -> None:
        await db_client.post("/api/v1/signup/request", json=_signup_payload())
        signup = await _fetch_signup_by_email(db_session, "applicant@example.com")
        role = await _chemical_engineer_role(db_session)
        await db_client.post(
            f"/api/v1/signup/admin/{signup.id}/approve",
            json={"role_id": str(role.id)},
        )
        await db_session.refresh(signup)
        token = signup.invite_token
        assert token

        resp = await db_client.get(f"/api/v1/signup/invite/validate?token={token}")
        assert resp.status_code == 200
        body = resp.json()
        assert body["valid"] is True
        assert body["email"] == "applicant@example.com"

        await db_session.refresh(signup)
        assert signup.status == "approved"

    @pytest.mark.asyncio
    async def test_validate_invite_with_bad_token_returns_invalid(self, db_client: AsyncClient) -> None:
        resp = await db_client.get("/api/v1/signup/invite/validate?token=garbage")
        assert resp.status_code == 200
        body = resp.json()
        assert body["valid"] is False
        assert body["email"] == ""
