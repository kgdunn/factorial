"""Unit tests for ``app.services.byok_service``.

Pure crypto, no DB. Verifies the three-layer keying scheme round-trips
correctly and that every failure mode that should fail closed actually
does — silent garbage on a wrong key would be a security regression.
"""

from __future__ import annotations

import base64

import pytest

from app.services import byok_service as bk
from app.services.byok_service import (
    BYOKConfigurationError,
    BYOKDecryptionError,
)


# ---------------------------------------------------------------------------
# Fast Argon2id parameters for tests.
# Production defaults take ~250 ms per derivation; that adds up across a
# full test suite. These are only used inside this module.
# ---------------------------------------------------------------------------


_FAST_PARAMS = {
    "variant": "argon2id",
    "m": 8,  # 8 KiB
    "t": 1,
    "p": 1,
}


class TestRandomKeyMaterial:
    def test_generate_dek_is_32_bytes(self):
        assert len(bk.generate_dek()) == 32

    def test_generate_session_key_is_32_bytes(self):
        assert len(bk.generate_session_key()) == 32

    def test_generate_kek_salt_is_16_bytes(self):
        assert len(bk.generate_kek_salt()) == 16

    def test_each_call_returns_fresh_bytes(self):
        # Birthday-bound: two consecutive 32-byte draws colliding is
        # roughly 2^-256. If this ever fails, something is very wrong.
        assert bk.generate_dek() != bk.generate_dek()
        assert bk.generate_session_key() != bk.generate_session_key()
        assert bk.generate_kek_salt() != bk.generate_kek_salt()


class TestArgon2id:
    def test_deterministic_for_same_inputs(self):
        salt = bk.generate_kek_salt()
        k1 = bk.derive_kek("hunter2", salt, _FAST_PARAMS)
        k2 = bk.derive_kek("hunter2", salt, _FAST_PARAMS)
        assert k1 == k2
        assert len(k1) == 32

    def test_different_password_yields_different_kek(self):
        salt = bk.generate_kek_salt()
        assert bk.derive_kek("hunter2", salt, _FAST_PARAMS) != bk.derive_kek("hunter3", salt, _FAST_PARAMS)

    def test_different_salt_yields_different_kek(self):
        s1 = bk.generate_kek_salt()
        s2 = bk.generate_kek_salt()
        assert bk.derive_kek("hunter2", s1, _FAST_PARAMS) != bk.derive_kek("hunter2", s2, _FAST_PARAMS)

    def test_unsupported_variant_raises(self):
        # Important: a corrupted or maliciously-tampered params blob must
        # not silently fall back to a weaker KDF.
        bad = {**_FAST_PARAMS, "variant": "bcrypt"}
        with pytest.raises(BYOKConfigurationError):
            bk.derive_kek("hunter2", bk.generate_kek_salt(), bad)

    def test_default_kdf_params_shape(self):
        params = bk.default_kdf_params()
        assert params["variant"] == "argon2id"
        assert isinstance(params["m"], int)
        assert isinstance(params["t"], int)
        assert isinstance(params["p"], int)


class TestTokenEncryption:
    def test_round_trip(self):
        dek = bk.generate_dek()
        token = "sk-ant-api03-XXXX"
        blob = bk.encrypt_token(token, dek)
        assert bk.decrypt_token(blob, dek) == token

    def test_blob_starts_with_random_nonce(self):
        dek = bk.generate_dek()
        b1 = bk.encrypt_token("sk-ant-api03-XXXX", dek)
        b2 = bk.encrypt_token("sk-ant-api03-XXXX", dek)
        # Same plaintext + key but different nonce -> different ciphertext.
        assert b1 != b2
        # The first 12 bytes are the nonce.
        assert b1[:12] != b2[:12]

    def test_wrong_dek_raises(self):
        dek = bk.generate_dek()
        wrong = bk.generate_dek()
        blob = bk.encrypt_token("sk-ant-api03-XXXX", dek)
        with pytest.raises(BYOKDecryptionError):
            bk.decrypt_token(blob, wrong)

    def test_truncated_blob_raises(self):
        dek = bk.generate_dek()
        blob = bk.encrypt_token("sk-ant-api03-XXXX", dek)
        with pytest.raises(BYOKDecryptionError):
            bk.decrypt_token(blob[:-1], dek)

    def test_tampered_ciphertext_raises(self):
        dek = bk.generate_dek()
        blob = bytearray(bk.encrypt_token("sk-ant-api03-XXXX", dek))
        blob[20] ^= 0x01
        with pytest.raises(BYOKDecryptionError):
            bk.decrypt_token(bytes(blob), dek)


class TestDekWrap:
    def test_round_trip(self):
        dek = bk.generate_dek()
        kek = bk.derive_kek("hunter2", bk.generate_kek_salt(), _FAST_PARAMS)
        wrapped = bk.wrap_dek(dek, kek)
        assert bk.unwrap_dek(wrapped, kek) == dek

    def test_wrong_password_unwrap_raises(self):
        dek = bk.generate_dek()
        salt = bk.generate_kek_salt()
        right_kek = bk.derive_kek("hunter2", salt, _FAST_PARAMS)
        wrong_kek = bk.derive_kek("hunter3", salt, _FAST_PARAMS)
        wrapped = bk.wrap_dek(dek, right_kek)
        # AEAD tag check must fail loudly — never return garbage bytes.
        with pytest.raises(BYOKDecryptionError):
            bk.unwrap_dek(wrapped, wrong_kek)

    def test_dek_must_be_32_bytes(self):
        kek = bk.derive_kek("hunter2", bk.generate_kek_salt(), _FAST_PARAMS)
        with pytest.raises(BYOKConfigurationError):
            bk.wrap_dek(b"\x00" * 31, kek)


class TestSessionDekWrap:
    def test_round_trip(self):
        dek = bk.generate_dek()
        sk = bk.generate_session_key()
        wrapped = bk.wrap_dek_for_session(dek, sk)
        assert bk.unwrap_dek_from_session(wrapped, sk) == dek

    def test_aad_isolation_between_persistent_and_session_wraps(self):
        # A wrapped-DEK blob produced for the persistent (KEK) wrap must
        # NOT decrypt under the per-session AAD even if an attacker
        # manages to coerce the same key bytes into both slots.
        key = bk.generate_dek()
        dek = bk.generate_dek()
        persistent = bk.wrap_dek(dek, key)
        with pytest.raises(BYOKDecryptionError):
            bk.unwrap_dek_from_session(persistent, key)


class TestMasterKey:
    def test_session_key_round_trip(self):
        master = bk.generate_session_key()  # any 32-byte buffer works
        sk = bk.generate_session_key()
        blob = bk.encrypt_session_key(sk, master)
        assert bk.decrypt_session_key(blob, master) == sk

    def test_wrong_master_key_raises(self):
        master = bk.generate_session_key()
        wrong = bk.generate_session_key()
        sk = bk.generate_session_key()
        blob = bk.encrypt_session_key(sk, master)
        with pytest.raises(BYOKDecryptionError):
            bk.decrypt_session_key(blob, wrong)

    def test_load_master_key_missing(self, monkeypatch):
        monkeypatch.setattr(bk.settings, "byok_master_key", "")
        with pytest.raises(BYOKConfigurationError):
            bk.load_master_key()

    def test_load_master_key_bad_base64(self, monkeypatch):
        monkeypatch.setattr(bk.settings, "byok_master_key", "not!!base64!!")
        with pytest.raises(BYOKConfigurationError):
            bk.load_master_key()

    def test_load_master_key_wrong_length(self, monkeypatch):
        # 16 zero bytes — valid base64, wrong size.
        monkeypatch.setattr(bk.settings, "byok_master_key", base64.b64encode(b"\x00" * 16).decode())
        with pytest.raises(BYOKConfigurationError):
            bk.load_master_key()

    def test_load_master_key_happy_path(self, monkeypatch):
        encoded = base64.b64encode(b"\x11" * 32).decode()
        monkeypatch.setattr(bk.settings, "byok_master_key", encoded)
        assert bk.load_master_key() == b"\x11" * 32


class TestEndToEndScenario:
    def test_login_decrypt_chat_flow(self):
        # Walks the full chain a chat request follows after enrollment +
        # login: persistent DEK wrap -> session DEK wrap -> token decrypt.
        password = "hunter2"
        salt = bk.generate_kek_salt()
        params = _FAST_PARAMS
        dek = bk.generate_dek()
        token_blob = bk.encrypt_token("sk-ant-api03-USER", dek)

        # At enrollment: wrap DEK under password-derived KEK.
        kek = bk.derive_kek(password, salt, params)
        dek_wrapped = bk.wrap_dek(dek, kek)

        # At login: re-derive KEK, unwrap DEK, re-wrap under session key.
        kek_again = bk.derive_kek(password, salt, params)
        dek_recovered = bk.unwrap_dek(dek_wrapped, kek_again)
        session_key = bk.generate_session_key()
        session_wrap = bk.wrap_dek_for_session(dek_recovered, session_key)
        master = b"\xab" * 32
        session_key_at_rest = bk.encrypt_session_key(session_key, master)

        # On chat: load session row, decrypt session key, unwrap DEK,
        # decrypt token. Token bytes never touched persistent storage
        # in plaintext.
        session_key_back = bk.decrypt_session_key(session_key_at_rest, master)
        dek_for_request = bk.unwrap_dek_from_session(session_wrap, session_key_back)
        assert bk.decrypt_token(token_blob, dek_for_request) == "sk-ant-api03-USER"
