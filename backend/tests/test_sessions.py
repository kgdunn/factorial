"""Tests for session_service and the cookie-based auth endpoints.

Mocks the DB layer end-to-end so the suite runs without Postgres.
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime, timedelta
from unittest.mock import AsyncMock, patch

import pytest

from app.api.csrf import CSRF_COOKIE_NAME, CSRF_HEADER_NAME, require_csrf
from app.api.deps import SESSION_COOKIE_NAME
from app.services import session_service
from app.services.session_service import (
    NewSession,
    csrf_tokens_match,
    lookup_session_by_cookie,
)

_USER = uuid.uuid4()


def _now() -> datetime:
    return datetime.now(UTC)


class _FakeSessionRow:
    """Mimics models.session.Session enough for service-layer logic."""

    def __init__(
        self,
        *,
        revoked: bool = False,
        idle_in: timedelta = timedelta(days=10),
        absolute_in: timedelta = timedelta(days=100),
        last_used_at: datetime | None = None,
    ):
        self.id = b"\x42" * 32
        self.public_id = uuid.uuid4()
        self.user_id = _USER
        self.family_id = uuid.uuid4()
        now = _now()
        self.created_at = now - timedelta(hours=1)
        self.last_used_at = last_used_at or now
        self.idle_expires_at = now + idle_in
        self.absolute_expires_at = now + absolute_in
        self.revoked_at = now if revoked else None
        self.user_agent = "pytest"
        self.ip = None


class _FakeResult:
    """Mimics SQLAlchemy Result for scalar_one_or_none()."""

    def __init__(self, value):
        self._value = value

    def scalar_one_or_none(self):
        return self._value


class _FakeDb:
    """Single-row stub: db.execute(...) → row; db.flush() is a no-op."""

    def __init__(self, row):
        self._row = row
        self.flush_calls = 0

    async def execute(self, _stmt):
        return _FakeResult(self._row)

    async def flush(self):
        self.flush_calls += 1


# ---------------------------------------------------------------------------
# session_service: lookup
# ---------------------------------------------------------------------------


class TestLookupSession:
    @pytest.mark.asyncio
    async def test_malformed_cookie_returns_none(self):
        db = _FakeDb(row=None)
        assert await lookup_session_by_cookie(db, "!!!not-base64!!!") is None

    @pytest.mark.asyncio
    async def test_unknown_session_returns_none(self):
        db = _FakeDb(row=None)
        # 32 zero bytes → 43-char base64url (no padding)
        assert await lookup_session_by_cookie(db, "A" * 43) is None

    @pytest.mark.asyncio
    async def test_revoked_session_returns_none(self):
        row = _FakeSessionRow(revoked=True)
        db = _FakeDb(row=row)
        assert await lookup_session_by_cookie(db, "A" * 43) is None

    @pytest.mark.asyncio
    async def test_idle_expired_session_returns_none(self):
        row = _FakeSessionRow(idle_in=timedelta(seconds=-1))
        db = _FakeDb(row=row)
        assert await lookup_session_by_cookie(db, "A" * 43) is None

    @pytest.mark.asyncio
    async def test_absolute_expired_session_returns_none(self):
        row = _FakeSessionRow(absolute_in=timedelta(seconds=-1))
        db = _FakeDb(row=row)
        assert await lookup_session_by_cookie(db, "A" * 43) is None

    @pytest.mark.asyncio
    async def test_active_session_returns_row_and_throttle(self):
        # last_used_at touched 30 seconds ago — under the 1-minute throttle.
        recent = _now() - timedelta(seconds=30)
        row = _FakeSessionRow(last_used_at=recent)
        db = _FakeDb(row=row)
        out = await lookup_session_by_cookie(db, "A" * 43)
        assert out is row
        assert db.flush_calls == 0  # throttle skipped the write

    @pytest.mark.asyncio
    async def test_active_session_writes_after_throttle_window(self):
        stale = _now() - timedelta(minutes=2)
        row = _FakeSessionRow(last_used_at=stale)
        db = _FakeDb(row=row)
        out = await lookup_session_by_cookie(db, "A" * 43)
        assert out is row
        assert db.flush_calls == 1  # throttle let the write through


# ---------------------------------------------------------------------------
# CSRF helper
# ---------------------------------------------------------------------------


class TestCsrfMatch:
    def test_empty_strings_do_not_match(self):
        assert not csrf_tokens_match("", "")

    def test_none_does_not_match(self):
        assert not csrf_tokens_match(None, "x")
        assert not csrf_tokens_match("x", None)

    def test_mismatch_rejected(self):
        assert not csrf_tokens_match("a", "b")

    def test_equal_tokens_match(self):
        assert csrf_tokens_match("abc", "abc")


# ---------------------------------------------------------------------------
# CSRF dependency (state-changing endpoint)
# ---------------------------------------------------------------------------


class TestCsrfDependency:
    @pytest.mark.asyncio
    async def test_get_is_exempt(self):
        from fastapi import Request

        scope = {"type": "http", "method": "GET", "headers": [], "cookies": {}}
        await require_csrf(Request(scope))  # no exception

    @pytest.mark.asyncio
    async def test_post_with_matching_header_and_cookie_passes(self):
        from fastapi import Request

        scope = {
            "type": "http",
            "method": "POST",
            "headers": [
                (b"x-csrf-token", b"shared"),
                (b"cookie", f"{CSRF_COOKIE_NAME}=shared".encode()),
            ],
        }
        await require_csrf(Request(scope))  # no exception

    @pytest.mark.asyncio
    async def test_post_without_header_is_rejected(self):
        from fastapi import HTTPException, Request

        scope = {
            "type": "http",
            "method": "POST",
            "headers": [
                (b"cookie", f"{CSRF_COOKIE_NAME}=shared".encode()),
            ],
        }
        with pytest.raises(HTTPException) as exc:
            await require_csrf(Request(scope))
        assert exc.value.status_code == 403

    @pytest.mark.asyncio
    async def test_post_with_api_key_skips_csrf(self):
        from fastapi import Request

        scope = {
            "type": "http",
            "method": "POST",
            "headers": [(b"x-api-key", b"any")],
        }
        await require_csrf(Request(scope))  # no exception


# ---------------------------------------------------------------------------
# /auth/logout — happy path via the test client
# ---------------------------------------------------------------------------


class TestLogout:
    @pytest.mark.asyncio
    async def test_logout_clears_cookies(self, client):
        """POST /auth/logout returns 204 and Sets expired cookies."""
        revoke = AsyncMock()
        with patch.object(session_service, "revoke_session", revoke):
            resp = await client.post(
                "/api/v1/auth/logout",
                headers={CSRF_HEADER_NAME: "x"},
                cookies={CSRF_COOKIE_NAME: "x", SESSION_COOKIE_NAME: "y"},
            )
        assert resp.status_code == 204
        # delete_cookie sets Max-Age=0 / expires in the past.
        joined = " ".join(resp.headers.get_list("set-cookie"))
        assert "factorial_session=" in joined
        assert "factorial_csrf=" in joined


# ---------------------------------------------------------------------------
# /auth/sessions — list + delete
# ---------------------------------------------------------------------------


class TestSessionsList:
    @pytest.mark.asyncio
    async def test_list_returns_public_ids_only(self, client):
        rows = [_FakeSessionRow(), _FakeSessionRow()]
        with patch.object(session_service, "list_user_sessions", AsyncMock(return_value=rows)):
            resp = await client.get(
                "/api/v1/auth/sessions",
                headers={CSRF_HEADER_NAME: "x"},
                cookies={CSRF_COOKIE_NAME: "x"},
            )
        assert resp.status_code == 200
        body = resp.json()
        assert len(body) == 2
        for entry in body:
            # public_id is a UUID string; raw id bytes never appear.
            uuid.UUID(entry["public_id"])
            assert "id" not in entry

    @pytest.mark.asyncio
    async def test_revoke_unknown_public_id_returns_404(self, client):
        with patch.object(
            session_service,
            "revoke_by_public_id",
            AsyncMock(return_value=False),
        ):
            resp = await client.delete(
                f"/api/v1/auth/sessions/{uuid.uuid4()}",
                headers={CSRF_HEADER_NAME: "x"},
                cookies={CSRF_COOKIE_NAME: "x"},
            )
        assert resp.status_code == 404


# ---------------------------------------------------------------------------
# create_session sanity
# ---------------------------------------------------------------------------


class TestCreateSessionShape:
    """create_session is integration-heavy; smoke-test the returned shape."""

    def test_new_session_dataclass(self):
        ns = NewSession(
            cookie_value="abc",
            csrf_token="def",  # noqa: S106
            session=_FakeSessionRow(),
        )
        assert ns.cookie_value == "abc"
        assert ns.csrf_token == "def"
        assert ns.session.user_id == _USER
