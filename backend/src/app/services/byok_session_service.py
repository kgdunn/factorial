"""DB-aware BYOK lifecycle helpers.

Composes the pure-crypto primitives in ``byok_service`` with the User /
Session ORM rows. Three operations are exposed:

- :func:`unwrap_for_login` — call after ``authenticate_user`` succeeds.
  Returns the two ciphertext blobs that must be written to the new
  ``sessions`` row, or ``(None, None)`` for users without an active
  enrollment.
- :func:`decrypt_token_for_request` — call when an authenticated request
  needs the user's plaintext API token (e.g. inside the chat path).
  Returns the token; raises ``BYOKDecryptionError`` if the session row
  is missing the wraps or the master key has rotated incompatibly.
- :func:`rewrap_dek_on_password_change` — call inside the password-change
  endpoint after the old password has been verified. Re-derives the KEK
  with the new password and re-wraps the same DEK; the long-lived token
  ciphertext is unchanged.

This module never returns the password, the KEK, or the DEK to its
callers. All key material lives only inside one stack frame and is
released as soon as the function returns.
"""

from __future__ import annotations

from app.models.session import Session
from app.models.user import User
from app.services import byok_service
from app.services.byok_service import (
    BYOKConfigurationError,
    BYOKDecryptionError,
)

# Status values mirror the docstring on ``User.byok_token_status``.
STATUS_ABSENT = "absent"
STATUS_ACTIVE = "active"
STATUS_REJECTED = "rejected"
STATUS_ORPHANED = "orphaned"


def _has_active_enrollment(user: User) -> bool:
    """A user is BYOK-active when status == active and all wraps are present.

    ``rejected`` users keep their ciphertexts but should not have their
    DEK unwrapped at login (the next chat would just 401 against
    Anthropic again). ``orphaned`` users have unrecoverable wraps and
    must re-enrol via the UI.
    """
    return (
        user.byok_token_status == STATUS_ACTIVE
        and user.byok_token_ciphertext is not None
        and user.byok_dek_wrapped is not None
        and user.byok_kek_salt is not None
        and user.byok_kdf_params is not None
    )


def unwrap_for_login(user: User, password: str) -> tuple[bytes | None, bytes | None]:
    """Produce the per-session BYOK wraps for a successful login.

    Returns ``(session_key_encrypted, dek_session_wrapped)`` ready to be
    written onto the new ``Session`` row, or ``(None, None)`` if the
    user has no active enrollment.

    Must be called only after the password has already been verified
    against ``user.password_hash`` — passing the wrong password here
    will raise ``BYOKDecryptionError`` from the AEAD tag check.
    """
    if not _has_active_enrollment(user):
        return None, None

    kek = byok_service.derive_kek(password, user.byok_kek_salt, user.byok_kdf_params)
    dek = byok_service.unwrap_dek(user.byok_dek_wrapped, kek)
    session_key = byok_service.generate_session_key()
    dek_session_wrapped = byok_service.wrap_dek_for_session(dek, session_key)
    master_key = byok_service.load_master_key()
    session_key_encrypted = byok_service.encrypt_session_key(session_key, master_key)
    return session_key_encrypted, dek_session_wrapped


def decrypt_token_for_request(user: User, session: Session) -> str:
    """Recover the plaintext Anthropic API token for a BYOK request.

    Walks the chain: master_key -> session_key -> DEK -> token. The
    plaintext lives only in the returned string; callers must hand it to
    the Anthropic SDK and let it fall out of scope immediately.

    Raises ``BYOKConfigurationError`` if the master key is unset, or
    ``BYOKDecryptionError`` if any wrap is corrupt, missing, or was
    encrypted under a different master key.
    """
    if user.byok_token_status != STATUS_ACTIVE or user.byok_token_ciphertext is None:
        raise BYOKDecryptionError("user has no active BYOK enrollment")
    if session.byok_session_key_encrypted is None or session.byok_dek_session_wrapped is None:
        raise BYOKDecryptionError("session has no BYOK wraps; user must sign in again")

    master_key = byok_service.load_master_key()
    session_key = byok_service.decrypt_session_key(session.byok_session_key_encrypted, master_key)
    dek = byok_service.unwrap_dek_from_session(session.byok_dek_session_wrapped, session_key)
    return byok_service.decrypt_token(user.byok_token_ciphertext, dek)


def rewrap_dek_on_password_change(user: User, old_password: str, new_password: str) -> None:
    """Re-wrap the user's DEK under a new password-derived KEK.

    Mutates the User row in place: ``byok_dek_wrapped`` is replaced with
    a fresh wrap; the salt and KDF params are kept unchanged so the
    on-disk format stays stable. The DEK and the token ciphertext are
    untouched, so an in-flight chat using a session-scoped wrap is
    unaffected.

    No-op for users without an active enrollment.

    Raises ``BYOKDecryptionError`` if the supplied ``old_password`` is
    wrong (the auth layer should have verified it already, but the AEAD
    check is the canonical truth).
    """
    if not _has_active_enrollment(user):
        return

    old_kek = byok_service.derive_kek(old_password, user.byok_kek_salt, user.byok_kdf_params)
    dek = byok_service.unwrap_dek(user.byok_dek_wrapped, old_kek)
    new_kek = byok_service.derive_kek(new_password, user.byok_kek_salt, user.byok_kdf_params)
    user.byok_dek_wrapped = byok_service.wrap_dek(dek, new_kek)


def orphan_dek(user: User) -> bool:
    """Mark the user's DEK as unrecoverable (called on password reset).

    Sets ``byok_token_status`` to ``orphaned`` so the UI prompts a
    re-enrolment on next sign-in. Leaves the ciphertexts in place so a
    later forensic check can confirm what the row contained, but no
    code path will try to decrypt them again.

    Returns True if the user actually had an active enrollment that was
    just orphaned, False otherwise. Idempotent — calling on an already-
    orphaned or absent row is a no-op.
    """
    if user.byok_token_status not in (STATUS_ACTIVE, STATUS_REJECTED):
        return False
    user.byok_token_status = STATUS_ORPHANED
    return True


__all__ = [
    "STATUS_ABSENT",
    "STATUS_ACTIVE",
    "STATUS_ORPHANED",
    "STATUS_REJECTED",
    "BYOKConfigurationError",
    "BYOKDecryptionError",
    "decrypt_token_for_request",
    "orphan_dek",
    "rewrap_dek_on_password_change",
    "unwrap_for_login",
]
