"""DB-aware BYOK lifecycle helpers.

Composes the pure-crypto primitives in ``byok_service`` with the User /
Session ORM rows. Public operations:

- :func:`unwrap_for_login` — produce per-session DEK wraps for a fresh
  ``sessions`` row at successful login.
- :func:`decrypt_token_for_request` — recover the plaintext token for
  the chat path.
- :func:`rewrap_dek_on_password_change` — rotate the wrapping KEK while
  preserving the DEK and the long-lived token ciphertext.
- :func:`orphan_dek` — mark the wraps unrecoverable on password reset.
- :func:`enroll` — first-time enrollment: encrypt the token, generate a
  fresh DEK, wrap it under the user's password.
- :func:`disable` — wipe all four user-side ciphertext columns.
- :func:`record_history` — append-only audit row.

This module never returns the password, the KEK, or the DEK to its
callers. All key material lives only inside one stack frame and is
released as soon as the function returns.
"""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession

from app.models.byok_credentials_history import BYOKCredentialsHistory
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

    Uses ``getattr`` with defaults so a not-yet-persisted ORM instance,
    or a test stub that does not set the BYOK columns explicitly,
    behaves the same as a row with ``status='absent'``.
    """
    return (
        getattr(user, "byok_token_status", STATUS_ABSENT) == STATUS_ACTIVE
        and getattr(user, "byok_token_ciphertext", None) is not None
        and getattr(user, "byok_dek_wrapped", None) is not None
        and getattr(user, "byok_kek_salt", None) is not None
        and getattr(user, "byok_kdf_params", None) is not None
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
    if (
        getattr(user, "byok_token_status", STATUS_ABSENT) != STATUS_ACTIVE
        or getattr(user, "byok_token_ciphertext", None) is None
    ):
        raise BYOKDecryptionError("user has no active BYOK enrollment")
    if (
        getattr(session, "byok_session_key_encrypted", None) is None
        or getattr(session, "byok_dek_session_wrapped", None) is None
    ):
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
    if getattr(user, "byok_token_status", STATUS_ABSENT) not in (STATUS_ACTIVE, STATUS_REJECTED):
        return False
    user.byok_token_status = STATUS_ORPHANED
    return True


def enroll(user: User, password: str, anthropic_api_key: str) -> None:
    """Land a fresh BYOK enrollment on the user row in place.

    Generates a new salt + DEK, wraps the DEK under a KEK derived from
    the supplied password (which must be the user's current password —
    the endpoint is responsible for verifying it before calling this),
    encrypts the API key under the DEK, and sets ``byok_token_status``
    to ``active``.

    Replaces any existing ciphertext on the row, which is the right
    behavior for ``POST /byok/rotate`` and for re-enrolment after an
    orphan / reject. The audit row in
    ``byok_credentials_history`` is left to the endpoint to write so
    rotation can record both the close-out of the old credential and
    the open of the new one in the same DB session.
    """
    salt = byok_service.generate_kek_salt()
    params = byok_service.default_kdf_params()
    kek = byok_service.derive_kek(password, salt, params)
    dek = byok_service.generate_dek()
    user.byok_kek_salt = salt
    user.byok_kdf_params = params
    user.byok_dek_wrapped = byok_service.wrap_dek(dek, kek)
    user.byok_token_ciphertext = byok_service.encrypt_token(anthropic_api_key, dek)
    user.byok_token_status = STATUS_ACTIVE


def disable(user: User) -> bool:
    """Wipe the user-side BYOK ciphertexts and revert status to ``absent``.

    Idempotent: returns ``False`` if there was nothing to wipe.
    Per-session DEK wraps in the ``sessions`` table are not touched
    here — they will fail to decrypt against the wiped user row at
    the next chat request and the chat path will fall back to the
    platform key. Operators who want immediate cutover should also
    revoke the user's active sessions via the existing
    ``revoke_family`` path.
    """
    had_something = (
        user.byok_token_ciphertext is not None
        or user.byok_dek_wrapped is not None
        or user.byok_kek_salt is not None
        or user.byok_kdf_params is not None
        or user.byok_token_status != STATUS_ABSENT
    )
    user.byok_token_ciphertext = None
    user.byok_dek_wrapped = None
    user.byok_kek_salt = None
    user.byok_kdf_params = None
    user.byok_token_last_verified_at = None
    user.byok_token_status = STATUS_ABSENT
    return had_something


def mark_verified(user: User) -> None:
    """Flip status to ``active`` and stamp ``last_verified_at = now``.

    Called from ``POST /byok/test`` and ``POST /byok/enroll`` after
    Anthropic returns OK on the verification ping.
    """
    user.byok_token_status = STATUS_ACTIVE
    user.byok_token_last_verified_at = datetime.now(UTC)


def mark_rejected(user: User) -> None:
    """Flip status to ``rejected`` after Anthropic rejects the key.

    The ciphertext stays in place so the UI can offer "re-enter your
    key" without losing the historical record. Rotation is delete-
    then-create elsewhere; rejection is a soft transition and does
    not destroy the wraps.
    """
    user.byok_token_status = STATUS_REJECTED


async def record_history(
    db: AsyncSession,
    *,
    user: User,
    action: str,
    extra: dict[str, Any] | None = None,
) -> None:
    """Append one audit row to ``byok_credentials_history``.

    Always writes ``status_after`` from the user's current
    ``byok_token_status``, so callers should mutate the user row first
    and then call this. ``extra`` is reserved for future fields and is
    currently ignored — kept on the signature so future audits (e.g.
    rotation reason codes) don't churn every call site.
    """
    del extra  # currently unused; reserved for future audit dimensions
    db.add(
        BYOKCredentialsHistory(
            user_id=user.id,
            action=action,
            status_after=getattr(user, "byok_token_status", STATUS_ABSENT),
            last_verified_at=getattr(user, "byok_token_last_verified_at", None),
        ),
    )


__all__ = [
    "STATUS_ABSENT",
    "STATUS_ACTIVE",
    "STATUS_ORPHANED",
    "STATUS_REJECTED",
    "BYOKConfigurationError",
    "BYOKDecryptionError",
    "decrypt_token_for_request",
    "disable",
    "enroll",
    "mark_rejected",
    "mark_verified",
    "orphan_dek",
    "record_history",
    "rewrap_dek_on_password_change",
    "unwrap_for_login",
]
