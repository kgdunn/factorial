"""BYOK (Bring-Your-Own-Key) cryptographic primitives.

Three keys protect a user's Anthropic API token:

1. **DEK** — 32 random bytes. AES-256-GCM-encrypts the token. Generated
   once at enrollment; long-lived; survives password changes (re-wrapped,
   not regenerated).
2. **KEK** — derived from the user's password via Argon2id. Wraps the
   DEK at rest. Re-derived on password change.
3. **Per-session DEK wrap** — a 32-byte session key generated at login,
   AES-GCM-wraps the DEK in the ``sessions`` row. The session key itself
   is encrypted at rest under ``settings.byok_master_key``.

This module is pure crypto and DB-agnostic — it operates on bytes/strings
only. Callers in ``auth_service`` / ``session_service`` / endpoints
compose these primitives with the persistence layer.

Threat model and design rationale: see
``docs/architecture/byok-anthropic-token.md``.
"""

from __future__ import annotations

import base64
import os
from typing import Any

from argon2.low_level import Type, hash_secret_raw
from cryptography.exceptions import InvalidTag
from cryptography.hazmat.primitives.ciphers.aead import AESGCM

from app.config import settings

# AES-GCM nonces are 12 bytes per NIST SP 800-38D. ``cryptography``
# concatenates the 16-byte tag onto the ciphertext, so the on-wire
# blob shape is ``nonce(12) || ciphertext || tag(16)``.
_NONCE_LEN = 12
_TAG_LEN = 16
_KEY_LEN = 32  # DEK / session key / master key

# Associated data for each AEAD usage. Binding the ciphertext to a
# context string prevents an attacker with DB access from swapping
# blobs across columns (e.g. moving a wrapped DEK into the token slot).
_AAD_TOKEN = b"byok.token.v1"
_AAD_DEK_WRAP = b"byok.dek-wrap.v1"
_AAD_SESSION_DEK_WRAP = b"byok.session-dek-wrap.v1"
_AAD_SESSION_KEY = b"byok.session-key-master.v1"


class BYOKError(Exception):
    """Base class for BYOK crypto failures."""


class BYOKDecryptionError(BYOKError):
    """Raised when AES-GCM authentication fails (wrong key, tampered blob,
    truncated input, or wrong AAD context).

    Never returns garbage bytes on failure — the GCM tag check catches
    every modification.
    """


class BYOKConfigurationError(BYOKError):
    """Raised when the runtime is misconfigured for BYOK (e.g. missing
    or malformed ``byok_master_key``)."""


# ---------------------------------------------------------------------------
# Random key material
# ---------------------------------------------------------------------------


def generate_dek() -> bytes:
    """A fresh 32-byte data encryption key."""
    return os.urandom(_KEY_LEN)


def generate_session_key() -> bytes:
    """A fresh 32-byte per-session DEK-wrap key."""
    return os.urandom(_KEY_LEN)


def generate_kek_salt() -> bytes:
    """A fresh 16-byte Argon2id salt."""
    return os.urandom(16)


# ---------------------------------------------------------------------------
# Argon2id password->KEK derivation
# ---------------------------------------------------------------------------


def default_kdf_params() -> dict[str, Any]:
    """Return the Argon2id parameter set in force right now.

    The returned dict is persisted on the user row alongside the salt so
    that later tuning of ``settings.byok_argon2_*`` does not break the
    ability to derive each user's existing KEK.
    """
    return {
        "variant": "argon2id",
        "m": settings.byok_argon2_memory_kib,
        "t": settings.byok_argon2_iterations,
        "p": settings.byok_argon2_parallelism,
    }


def derive_kek(password: str, salt: bytes, params: dict[str, Any]) -> bytes:
    """Derive a 32-byte KEK from ``password`` using Argon2id.

    ``params`` must carry ``variant``, ``m`` (memory cost in KiB), ``t``
    (iterations), and ``p`` (parallelism). Only ``argon2id`` is accepted;
    any other variant raises ``BYOKConfigurationError`` so a corrupted
    or maliciously-tampered params blob fails closed instead of silently
    falling back to a weaker KDF.
    """
    variant = params.get("variant")
    if variant != "argon2id":
        raise BYOKConfigurationError(f"Unsupported KDF variant: {variant!r}")
    return hash_secret_raw(
        secret=password.encode("utf-8"),
        salt=salt,
        time_cost=int(params["t"]),
        memory_cost=int(params["m"]),
        parallelism=int(params["p"]),
        hash_len=_KEY_LEN,
        type=Type.ID,
    )


# ---------------------------------------------------------------------------
# AES-GCM seal / open
# ---------------------------------------------------------------------------


def _seal(key: bytes, plaintext: bytes, aad: bytes) -> bytes:
    if len(key) != _KEY_LEN:
        raise BYOKConfigurationError(f"AEAD key must be {_KEY_LEN} bytes, got {len(key)}")
    nonce = os.urandom(_NONCE_LEN)
    ct = AESGCM(key).encrypt(nonce, plaintext, aad)
    return nonce + ct


def _open(key: bytes, blob: bytes, aad: bytes) -> bytes:
    if len(key) != _KEY_LEN:
        raise BYOKConfigurationError(f"AEAD key must be {_KEY_LEN} bytes, got {len(key)}")
    if len(blob) < _NONCE_LEN + _TAG_LEN:
        raise BYOKDecryptionError("ciphertext too short")
    nonce, ct = blob[:_NONCE_LEN], blob[_NONCE_LEN:]
    try:
        return AESGCM(key).decrypt(nonce, ct, aad)
    except InvalidTag as exc:
        raise BYOKDecryptionError("authentication failed") from exc


# ---------------------------------------------------------------------------
# Token at rest (encrypted under DEK)
# ---------------------------------------------------------------------------


def encrypt_token(token: str, dek: bytes) -> bytes:
    """AES-GCM-encrypt the API token under the DEK."""
    return _seal(dek, token.encode("utf-8"), _AAD_TOKEN)


def decrypt_token(blob: bytes, dek: bytes) -> str:
    """Decrypt and decode an API token blob produced by ``encrypt_token``.

    Raises ``BYOKDecryptionError`` on any tampering, truncation, or
    wrong-DEK attempt.
    """
    return _open(dek, blob, _AAD_TOKEN).decode("utf-8")


# ---------------------------------------------------------------------------
# DEK wrap (under password-derived KEK; long-lived)
# ---------------------------------------------------------------------------


def wrap_dek(dek: bytes, kek: bytes) -> bytes:
    """Wrap the DEK under the password-derived KEK for storage."""
    if len(dek) != _KEY_LEN:
        raise BYOKConfigurationError(f"DEK must be {_KEY_LEN} bytes, got {len(dek)}")
    return _seal(kek, dek, _AAD_DEK_WRAP)


def unwrap_dek(blob: bytes, kek: bytes) -> bytes:
    """Recover the DEK from a wrapped blob.

    Raises ``BYOKDecryptionError`` if the supplied ``kek`` is wrong
    (typically: the user typed an incorrect password).
    """
    return _open(kek, blob, _AAD_DEK_WRAP)


# ---------------------------------------------------------------------------
# Per-session DEK wrap (under session-scoped key; short-lived)
# ---------------------------------------------------------------------------


def wrap_dek_for_session(dek: bytes, session_key: bytes) -> bytes:
    """Wrap the DEK under a per-session key for the ``sessions`` row."""
    return _seal(session_key, dek, _AAD_SESSION_DEK_WRAP)


def unwrap_dek_from_session(blob: bytes, session_key: bytes) -> bytes:
    """Recover the DEK from a per-session wrap."""
    return _open(session_key, blob, _AAD_SESSION_DEK_WRAP)


# ---------------------------------------------------------------------------
# Master-key encryption of the per-session key
# ---------------------------------------------------------------------------


def load_master_key() -> bytes:
    """Return the configured ``BYOK_MASTER_KEY`` as raw bytes.

    The setting carries a base64-encoded 32-byte key. Raises
    ``BYOKConfigurationError`` if missing, wrong length, or not valid
    base64. Callers that legitimately need to operate on BYOK material
    must surface this error — fail closed rather than silently falling
    back to plaintext storage.
    """
    raw = settings.byok_master_key
    if not raw:
        raise BYOKConfigurationError("BYOK_MASTER_KEY is not configured")
    try:
        decoded = base64.b64decode(raw, validate=True)
    except (ValueError, base64.binascii.Error) as exc:
        raise BYOKConfigurationError("BYOK_MASTER_KEY is not valid base64") from exc
    if len(decoded) != _KEY_LEN:
        raise BYOKConfigurationError(f"BYOK_MASTER_KEY must decode to {_KEY_LEN} bytes, got {len(decoded)}")
    return decoded


def encrypt_session_key(session_key: bytes, master_key: bytes) -> bytes:
    """Encrypt a per-session DEK-wrap key under the server master key."""
    if len(session_key) != _KEY_LEN:
        raise BYOKConfigurationError(f"session key must be {_KEY_LEN} bytes, got {len(session_key)}")
    return _seal(master_key, session_key, _AAD_SESSION_KEY)


def decrypt_session_key(blob: bytes, master_key: bytes) -> bytes:
    """Recover a per-session DEK-wrap key encrypted by ``encrypt_session_key``."""
    return _open(master_key, blob, _AAD_SESSION_KEY)
