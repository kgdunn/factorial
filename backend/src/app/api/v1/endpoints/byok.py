"""Bring-Your-Own Anthropic API token endpoints.

Five operations under ``/api/v1/byok``:

- ``GET    /``        — public status for the profile UI
- ``POST   /enroll``  — first-time enrollment (or replace after orphan)
- ``POST   /test``    — re-verify the stored key against Anthropic
- ``POST   /rotate``  — replace the stored key (delete-then-create audit
  shape)
- ``DELETE /``        — wipe the stored key and revert to the platform
  path

All endpoints require an authenticated cookie session (``require_auth``)
and CSRF (``require_csrf``) — applied at the router level alongside
the other ``_auth`` routers in ``api/v1/router.py``.

The endpoints intentionally never log or return key material, the
plaintext password, or any of the wrap blobs. The structured-log filter
landing in this PR is a defence-in-depth backstop, not the primary
guarantee.
"""

from __future__ import annotations

import logging

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import AuthUser, require_auth
from app.db.session import get_db_session
from app.schemas.byok import BYOKEnrollRequest, BYOKStatusResponse, BYOKTestResponse
from app.services import byok_anthropic_service, byok_session_service
from app.services.auth_service import verify_password
from app.services.byok_anthropic_service import VerificationOutcome
from app.services.byok_service import BYOKConfigurationError, BYOKDecryptionError

logger = logging.getLogger(__name__)

router = APIRouter()


def _public_status(user) -> BYOKStatusResponse:
    """Build the GET-/byok response from the user row."""
    return BYOKStatusResponse(
        status=getattr(user, "byok_token_status", byok_session_service.STATUS_ABSENT),
        last_verified_at=getattr(user, "byok_token_last_verified_at", None),
    )


async def _load_user(db: AsyncSession, current_user: AuthUser):
    """Fetch the live User row for the authenticated caller.

    A 404 here would be a programming error (the auth dependency just
    confirmed the session exists), so we 500-style raise with a generic
    message rather than leaking detail.
    """
    from app.models.user import User

    user = await db.get(User, current_user.id)
    if user is None:
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="User not found")
    return user


@router.get("", response_model=BYOKStatusResponse)
async def get_status(
    current_user: AuthUser = Depends(require_auth),
    db: AsyncSession = Depends(get_db_session),
) -> BYOKStatusResponse:
    """Return the user's BYOK status and last-verified timestamp."""
    user = await _load_user(db, current_user)
    return _public_status(user)


@router.post("/enroll", response_model=BYOKStatusResponse)
async def enroll(
    body: BYOKEnrollRequest,
    current_user: AuthUser = Depends(require_auth),
    db: AsyncSession = Depends(get_db_session),
) -> BYOKStatusResponse:
    """Land a fresh BYOK enrollment for the current user.

    Re-verifies the password (the active session does not carry it),
    pings Anthropic with the submitted key to confirm it is valid,
    encrypts and persists the wraps, writes an audit row.
    """
    user = await _load_user(db, current_user)
    if not user.password_hash or not verify_password(body.password, user.password_hash):
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Current password is incorrect")

    outcome = byok_anthropic_service.verify_with_anthropic(body.anthropic_api_key)
    if outcome is VerificationOutcome.REJECTED:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Anthropic rejected the key. Double-check the value and try again.",
        )
    if outcome is VerificationOutcome.TRANSIENT:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Couldn't reach Anthropic to verify the key. Try again in a moment.",
        )

    byok_session_service.enroll(user, body.password, body.anthropic_api_key)
    byok_session_service.mark_verified(user)
    await byok_session_service.record_history(db, user=user, action="enrolled")
    return _public_status(user)


@router.post("/rotate", response_model=BYOKStatusResponse)
async def rotate(
    body: BYOKEnrollRequest,
    current_user: AuthUser = Depends(require_auth),
    db: AsyncSession = Depends(get_db_session),
) -> BYOKStatusResponse:
    """Replace the stored key with a new one.

    Same crypto contract as enroll — the previous DEK and wrapping KEK
    are discarded and re-derived. Modeled in the audit log as a close
    of the old credential plus an open of the new one so admins see
    clear ``[t1, t2)`` intervals per credential.
    """
    user = await _load_user(db, current_user)
    if not user.password_hash or not verify_password(body.password, user.password_hash):
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Current password is incorrect")

    outcome = byok_anthropic_service.verify_with_anthropic(body.anthropic_api_key)
    if outcome is VerificationOutcome.REJECTED:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Anthropic rejected the new key. Double-check the value and try again.",
        )
    if outcome is VerificationOutcome.TRANSIENT:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Couldn't reach Anthropic to verify the new key. Try again in a moment.",
        )

    if user.byok_token_ciphertext is not None:
        await byok_session_service.record_history(db, user=user, action="rotated_out")
    byok_session_service.enroll(user, body.password, body.anthropic_api_key)
    byok_session_service.mark_verified(user)
    await byok_session_service.record_history(db, user=user, action="rotated_in")
    return _public_status(user)


@router.post("/test", response_model=BYOKTestResponse)
async def test_key(
    current_user: AuthUser = Depends(require_auth),
    db: AsyncSession = Depends(get_db_session),
) -> BYOKTestResponse:
    """Verify the stored key with Anthropic, update status, audit.

    Decrypts via the current session's DEK wraps (does not require the
    user to re-enter their password) and pings Anthropic. Rejected
    keys flip to status='rejected'; transient failures leave status
    untouched so a brief Anthropic outage doesn't disable a user's
    enrollment.
    """
    user = await _load_user(db, current_user)
    if user.byok_token_status == byok_session_service.STATUS_ABSENT:
        return BYOKTestResponse(outcome="no_key", status=user.byok_token_status, last_verified_at=None)

    # Need the session row to unwrap the DEK.
    from app.models.session import Session as SessionRow

    if current_user.session_id is None:
        return BYOKTestResponse(outcome="no_key", status=user.byok_token_status, last_verified_at=None)
    session_row = await db.get(SessionRow, current_user.session_id)
    if session_row is None:
        return BYOKTestResponse(outcome="no_key", status=user.byok_token_status, last_verified_at=None)

    try:
        token = byok_session_service.decrypt_token_for_request(user, session_row)
    except (BYOKDecryptionError, BYOKConfigurationError):
        # Wraps are unrecoverable on this session — treat as no_key
        # rather than transient. The UI will prompt re-enrol or
        # re-sign-in.
        return BYOKTestResponse(outcome="no_key", status=user.byok_token_status, last_verified_at=None)

    outcome = byok_anthropic_service.verify_with_anthropic(token)
    if outcome is VerificationOutcome.OK:
        byok_session_service.mark_verified(user)
        await byok_session_service.record_history(db, user=user, action="verified")
        return BYOKTestResponse(
            outcome="ok",
            status=user.byok_token_status,
            last_verified_at=user.byok_token_last_verified_at,
        )
    if outcome is VerificationOutcome.REJECTED:
        byok_session_service.mark_rejected(user)
        await byok_session_service.record_history(db, user=user, action="rejected")
        return BYOKTestResponse(
            outcome="rejected",
            status=user.byok_token_status,
            last_verified_at=user.byok_token_last_verified_at,
        )
    return BYOKTestResponse(
        outcome="transient",
        status=user.byok_token_status,
        last_verified_at=user.byok_token_last_verified_at,
    )


@router.delete("", status_code=status.HTTP_204_NO_CONTENT)
async def delete_enrollment(
    current_user: AuthUser = Depends(require_auth),
    db: AsyncSession = Depends(get_db_session),
) -> None:
    """Wipe the BYOK enrollment for the current user.

    Idempotent. Audit row is written only if there was something to
    wipe so the trail doesn't fill with no-op deletes.
    """
    user = await _load_user(db, current_user)
    had_something = byok_session_service.disable(user)
    if had_something:
        await byok_session_service.record_history(db, user=user, action="removed")
