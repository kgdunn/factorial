"""Unit tests for ``app.services.byok_session_service``.

Operates on in-memory User and Session ORM instances — no DB needed.
The composition layer is pure Python over byok_service primitives, so
tests verify wiring (which blob goes where, status transitions, fail-
closed behavior) without needing aiosqlite fixtures.
"""

from __future__ import annotations

import base64

import pytest

from app.models.session import Session
from app.models.user import User
from app.services import byok_service, byok_session_service
from app.services.byok_service import BYOKConfigurationError, BYOKDecryptionError
from app.services.byok_session_service import (
    STATUS_ABSENT,
    STATUS_ACTIVE,
    STATUS_ORPHANED,
    STATUS_REJECTED,
)

# Fast Argon2id params so the suite stays under a second; production
# values would otherwise add ~250 ms per derivation.
_FAST_PARAMS = {"variant": "argon2id", "m": 8, "t": 1, "p": 1}
_PASSWORD = "hunter2"  # noqa: S105
_TOKEN = "sk-ant-api03-USER"
_MASTER_KEY_B64 = base64.b64encode(b"\xab" * 32).decode()


@pytest.fixture
def master_key(monkeypatch):
    """Configure a BYOK_MASTER_KEY for the duration of the test."""
    monkeypatch.setattr(byok_service.settings, "byok_master_key", _MASTER_KEY_B64)
    return _MASTER_KEY_B64


def _enrolled_user(password: str = _PASSWORD, token: str = _TOKEN) -> User:
    """Build a User instance carrying a fully-formed BYOK enrollment.

    Mirrors what ``POST /byok/enroll`` will land (PR 3) so the auth
    wiring tests have something realistic to operate on.
    """
    salt = byok_service.generate_kek_salt()
    kek = byok_service.derive_kek(password, salt, _FAST_PARAMS)
    dek = byok_service.generate_dek()
    user = User(
        email="alice@example.com",
        password_hash="bcrypt-hash-not-used-here",  # noqa: S106 — placeholder, never verified
        byok_token_ciphertext=byok_service.encrypt_token(token, dek),
        byok_dek_wrapped=byok_service.wrap_dek(dek, kek),
        byok_kek_salt=salt,
        byok_kdf_params=_FAST_PARAMS,
        byok_token_status=STATUS_ACTIVE,
    )
    return user


def _absent_user() -> User:
    """A user with no BYOK enrollment (the common case)."""
    return User(
        email="bob@example.com",
        password_hash="bcrypt-hash-not-used-here",  # noqa: S106 — placeholder, never verified
        byok_token_status=STATUS_ABSENT,
    )


class TestUnwrapForLogin:
    def test_returns_none_for_absent_user(self, master_key):
        user = _absent_user()
        assert byok_session_service.unwrap_for_login(user, "anything") == (None, None)

    def test_returns_none_for_user_with_no_attributes_set(self, master_key):
        # _has_active_enrollment uses getattr defaults so an unpersisted
        # User() (no BYOK fields explicitly set) behaves as 'absent'.
        user = User(email="x@y.com", password_hash="h")  # noqa: S106 — placeholder, never verified
        assert byok_session_service.unwrap_for_login(user, "anything") == (None, None)

    def test_returns_blobs_for_active_user(self, master_key):
        user = _enrolled_user()
        sk_enc, dek_wrap = byok_session_service.unwrap_for_login(user, _PASSWORD)
        assert isinstance(sk_enc, bytes) and len(sk_enc) > 32
        assert isinstance(dek_wrap, bytes) and len(dek_wrap) > 32

    def test_each_login_produces_fresh_session_key(self, master_key):
        user = _enrolled_user()
        a_sk, a_wrap = byok_session_service.unwrap_for_login(user, _PASSWORD)
        b_sk, b_wrap = byok_session_service.unwrap_for_login(user, _PASSWORD)
        assert a_sk != b_sk
        assert a_wrap != b_wrap

    def test_wrong_password_fails_closed(self, master_key):
        user = _enrolled_user()
        with pytest.raises(BYOKDecryptionError):
            byok_session_service.unwrap_for_login(user, "wrong-password")

    def test_rejected_user_is_treated_as_absent(self, master_key):
        # Rejected enrollments keep their ciphertext but should not
        # be unwrapped at login (next chat would 401 again).
        user = _enrolled_user()
        user.byok_token_status = STATUS_REJECTED
        assert byok_session_service.unwrap_for_login(user, _PASSWORD) == (None, None)

    def test_orphaned_user_is_treated_as_absent(self, master_key):
        user = _enrolled_user()
        user.byok_token_status = STATUS_ORPHANED
        assert byok_session_service.unwrap_for_login(user, _PASSWORD) == (None, None)

    def test_missing_master_key_raises_configuration_error(self, monkeypatch):
        monkeypatch.setattr(byok_service.settings, "byok_master_key", "")
        user = _enrolled_user()
        with pytest.raises(BYOKConfigurationError):
            byok_session_service.unwrap_for_login(user, _PASSWORD)


class TestDecryptTokenForRequest:
    def test_round_trip_through_session(self, master_key):
        user = _enrolled_user()
        sk_enc, dek_wrap = byok_session_service.unwrap_for_login(user, _PASSWORD)
        session = Session(
            id=b"\x00" * 32,
            user_id=user.id,
            byok_session_key_encrypted=sk_enc,
            byok_dek_session_wrapped=dek_wrap,
        )
        assert byok_session_service.decrypt_token_for_request(user, session) == _TOKEN

    def test_raises_when_user_not_active(self, master_key):
        user = _enrolled_user()
        user.byok_token_status = STATUS_ABSENT
        session = Session(
            id=b"\x00" * 32,
            user_id=user.id,
            byok_session_key_encrypted=b"\x00" * 60,
            byok_dek_session_wrapped=b"\x00" * 60,
        )
        with pytest.raises(BYOKDecryptionError):
            byok_session_service.decrypt_token_for_request(user, session)

    def test_raises_when_session_missing_wraps(self, master_key):
        user = _enrolled_user()
        session = Session(id=b"\x00" * 32, user_id=user.id)
        with pytest.raises(BYOKDecryptionError):
            byok_session_service.decrypt_token_for_request(user, session)

    def test_raises_under_rotated_master_key(self, master_key, monkeypatch):
        # Wraps were produced under one master key; if BYOK_MASTER_KEY
        # is rotated without re-encrypting session rows, they fail
        # closed rather than silently returning garbage.
        user = _enrolled_user()
        sk_enc, dek_wrap = byok_session_service.unwrap_for_login(user, _PASSWORD)
        session = Session(
            id=b"\x00" * 32,
            user_id=user.id,
            byok_session_key_encrypted=sk_enc,
            byok_dek_session_wrapped=dek_wrap,
        )
        monkeypatch.setattr(
            byok_service.settings,
            "byok_master_key",
            base64.b64encode(b"\xcd" * 32).decode(),
        )
        with pytest.raises(BYOKDecryptionError):
            byok_session_service.decrypt_token_for_request(user, session)


class TestRewrapOnPasswordChange:
    def test_noop_for_absent_user(self):
        user = _absent_user()
        byok_session_service.rewrap_dek_on_password_change(user, "old", "new")
        assert user.byok_dek_wrapped is None  # untouched

    def test_replaces_wrapped_dek_in_place(self, master_key):
        user = _enrolled_user(_PASSWORD)
        before = user.byok_dek_wrapped
        byok_session_service.rewrap_dek_on_password_change(user, _PASSWORD, "newpass")
        assert user.byok_dek_wrapped != before
        assert user.byok_token_ciphertext  # unchanged
        assert user.byok_kek_salt  # unchanged
        assert user.byok_kdf_params  # unchanged

    def test_login_works_with_new_password_and_fails_with_old(self, master_key):
        user = _enrolled_user(_PASSWORD)
        byok_session_service.rewrap_dek_on_password_change(user, _PASSWORD, "newpass")

        # Login with the new password decrypts cleanly end-to-end.
        sk_enc, dek_wrap = byok_session_service.unwrap_for_login(user, "newpass")
        session = Session(
            id=b"\x00" * 32,
            user_id=user.id,
            byok_session_key_encrypted=sk_enc,
            byok_dek_session_wrapped=dek_wrap,
        )
        assert byok_session_service.decrypt_token_for_request(user, session) == _TOKEN

        # The old password no longer unwraps the (re-wrapped) DEK.
        with pytest.raises(BYOKDecryptionError):
            byok_session_service.unwrap_for_login(user, _PASSWORD)

    def test_wrong_old_password_fails_closed(self, master_key):
        user = _enrolled_user(_PASSWORD)
        with pytest.raises(BYOKDecryptionError):
            byok_session_service.rewrap_dek_on_password_change(user, "wrong-old", "new")


class TestOrphanDek:
    def test_active_user_becomes_orphaned(self):
        user = _enrolled_user()
        assert byok_session_service.orphan_dek(user) is True
        assert user.byok_token_status == STATUS_ORPHANED
        # Ciphertexts kept for forensics — not silently scrubbed.
        assert user.byok_token_ciphertext is not None
        assert user.byok_dek_wrapped is not None

    def test_rejected_user_can_be_orphaned(self):
        user = _enrolled_user()
        user.byok_token_status = STATUS_REJECTED
        assert byok_session_service.orphan_dek(user) is True
        assert user.byok_token_status == STATUS_ORPHANED

    def test_already_orphaned_is_noop(self):
        user = _enrolled_user()
        user.byok_token_status = STATUS_ORPHANED
        assert byok_session_service.orphan_dek(user) is False
        assert user.byok_token_status == STATUS_ORPHANED

    def test_absent_user_is_noop(self):
        user = _absent_user()
        assert byok_session_service.orphan_dek(user) is False
        assert user.byok_token_status == STATUS_ABSENT
