"""Tests for the DB-aware lifecycle helpers in ``byok_session_service``.

Covers ``enroll`` / ``disable`` / ``mark_verified`` / ``mark_rejected`` /
``record_history`` against the shared transactional Postgres
``db_session`` fixture (see ``conftest.py``).
"""

from __future__ import annotations

import base64
from datetime import UTC, datetime

import pytest
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.byok_credentials_history import BYOKCredentialsHistory
from app.models.user import User
from app.services import byok_service, byok_session_service
from app.services.byok_session_service import (
    STATUS_ABSENT,
    STATUS_ACTIVE,
    STATUS_REJECTED,
)

_PASSWORD = "hunter2"
_KEY = "sk-ant-api03-USERKEY"
_KEY_ALT = "sk-ant-api03-ANOTHER"


@pytest.fixture
def master_key(monkeypatch):
    """Configure BYOK_MASTER_KEY for tests that exercise master-key crypto."""
    monkeypatch.setattr(
        byok_service.settings,
        "byok_master_key",
        base64.b64encode(b"\x77" * 32).decode(),
    )


async def _seed_user(db: AsyncSession, email: str = "alice@example.com") -> User:
    """Land an empty (no BYOK) user row."""
    user = User(
        email=email,
        password_hash="bcrypt-hash-not-checked",  # noqa: S106 — placeholder
        display_name="Alice",
        is_active=True,
    )
    db.add(user)
    await db.flush()
    return user


# Smaller Argon2id params used inside enroll() come from
# byok_service.default_kdf_params(), which is driven by config.
# Override settings so enroll() runs in milliseconds.
@pytest.fixture(autouse=True)
def fast_kdf(monkeypatch):
    monkeypatch.setattr(byok_service.settings, "byok_argon2_memory_kib", 8)
    monkeypatch.setattr(byok_service.settings, "byok_argon2_iterations", 1)
    monkeypatch.setattr(byok_service.settings, "byok_argon2_parallelism", 1)


class TestEnroll:
    async def test_lands_a_full_enrollment(self, db_session, master_key):
        user = await _seed_user(db_session)
        byok_session_service.enroll(user, password=_PASSWORD, anthropic_api_key=_KEY)
        assert user.byok_token_status == STATUS_ACTIVE
        assert user.byok_token_ciphertext is not None
        assert user.byok_dek_wrapped is not None
        assert user.byok_kek_salt is not None
        assert user.byok_kdf_params is not None

    async def test_login_can_decrypt_after_enroll(self, db_session, master_key):
        user = await _seed_user(db_session)
        byok_session_service.enroll(user, password=_PASSWORD, anthropic_api_key=_KEY)
        sk_enc, dek_wrap = byok_session_service.unwrap_for_login(user, _PASSWORD)
        assert sk_enc and dek_wrap

    async def test_replaces_existing_enrollment(self, db_session, master_key):
        user = await _seed_user(db_session)
        byok_session_service.enroll(user, password=_PASSWORD, anthropic_api_key=_KEY)
        first = user.byok_token_ciphertext
        byok_session_service.enroll(user, password=_PASSWORD, anthropic_api_key=_KEY_ALT)
        assert user.byok_token_ciphertext != first


class TestDisable:
    async def test_wipes_all_columns_and_returns_true(self, db_session, master_key):
        user = await _seed_user(db_session)
        byok_session_service.enroll(user, password=_PASSWORD, anthropic_api_key=_KEY)
        assert byok_session_service.disable(user) is True
        assert user.byok_token_status == STATUS_ABSENT
        assert user.byok_token_ciphertext is None
        assert user.byok_dek_wrapped is None
        assert user.byok_kek_salt is None
        assert user.byok_kdf_params is None
        assert user.byok_token_last_verified_at is None

    async def test_idempotent_returns_false_when_nothing_to_wipe(self, db_session):
        user = await _seed_user(db_session)
        assert byok_session_service.disable(user) is False


class TestMarkers:
    async def test_mark_verified_stamps_now_and_flips_active(self, db_session, master_key):
        user = await _seed_user(db_session)
        byok_session_service.enroll(user, password=_PASSWORD, anthropic_api_key=_KEY)
        before = datetime.now(UTC)
        byok_session_service.mark_verified(user)
        assert user.byok_token_status == STATUS_ACTIVE
        assert user.byok_token_last_verified_at is not None
        assert user.byok_token_last_verified_at >= before

    async def test_mark_rejected_does_not_destroy_ciphertext(self, db_session, master_key):
        user = await _seed_user(db_session)
        byok_session_service.enroll(user, password=_PASSWORD, anthropic_api_key=_KEY)
        before_ct = user.byok_token_ciphertext
        byok_session_service.mark_rejected(user)
        assert user.byok_token_status == STATUS_REJECTED
        assert user.byok_token_ciphertext == before_ct


class TestRecordHistory:
    async def test_appends_one_row_per_call(self, db_session, master_key):
        user = await _seed_user(db_session)
        await byok_session_service.record_history(db_session, user=user, action="enrolled")
        await byok_session_service.record_history(db_session, user=user, action="verified")
        await db_session.flush()
        rows = (
            (await db_session.execute(select(BYOKCredentialsHistory).where(BYOKCredentialsHistory.user_id == user.id)))
            .scalars()
            .all()
        )
        assert {r.action for r in rows} == {"enrolled", "verified"}

    async def test_status_after_mirrors_user_row(self, db_session, master_key):
        user = await _seed_user(db_session)
        byok_session_service.enroll(user, password=_PASSWORD, anthropic_api_key=_KEY)
        byok_session_service.mark_verified(user)
        await byok_session_service.record_history(db_session, user=user, action="enrolled")
        await db_session.flush()
        row = (await db_session.execute(select(BYOKCredentialsHistory))).scalars().first()
        assert row is not None
        assert row.status_after == STATUS_ACTIVE
        assert row.last_verified_at is not None
        # Strip tzinfo for the comparison so the assertion stays portable
        # if the test DB driver ever returns naive datetimes.
        assert row.last_verified_at.replace(tzinfo=None) == user.byok_token_last_verified_at.replace(tzinfo=None)
