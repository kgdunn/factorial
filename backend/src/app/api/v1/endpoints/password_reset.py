"""Password reset + first-time setup endpoints.

Shared between:

- First-time admin bootstrap (``purpose="setup"`` tokens issued by the CLI)
- Ordinary password reset for existing users (``purpose="reset"`` tokens
  issued by ``POST /auth/password-reset/request`` or the admin UI).
"""

from __future__ import annotations

import contextlib
import logging

from fastapi import APIRouter, Depends, HTTPException, Query, Request, Response, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.auth_cookies import set_session_cookies
from app.api.deps import AuthUser, require_auth
from app.api.rate_limit import limiter
from app.config import settings
from app.db.session import get_db_session
from app.schemas.auth import (
    PasswordChangePayload,
    PasswordResetCompletePayload,
    PasswordResetRequestPayload,
    PasswordResetValidateResponse,
    UserResponse,
)
from app.services import balance_service, byok_session_service, session_service, setup_token_service
from app.services.auth_service import hash_password, verify_password
from app.services.byok_service import BYOKDecryptionError
from app.services.email_service import send_setup_email

logger = logging.getLogger(__name__)

router = APIRouter()


@router.post("/password-reset/request", status_code=status.HTTP_202_ACCEPTED)
@limiter.limit(settings.auth_rate_limit)
async def request_password_reset(
    request: Request,
    body: PasswordResetRequestPayload,
    db: AsyncSession = Depends(get_db_session),
) -> dict[str, str]:
    """Issue a reset link for the given email if it corresponds to an active user.

    Always returns 202 regardless of whether the email exists, to avoid
    user-enumeration.
    """
    user = await setup_token_service.find_active_user_by_email(db, body.email)
    if user is not None:
        token = await setup_token_service.issue_token(db, user, setup_token_service.RESET)
        url = await setup_token_service.build_setup_url(token)
        with contextlib.suppress(Exception):
            await send_setup_email(user.email, url, is_first_time=False)
    return {"message": "If that email exists, a reset link has been sent."}


@router.get("/setup/validate", response_model=PasswordResetValidateResponse)
async def validate_setup_token(
    token: str = Query(...),
    db: AsyncSession = Depends(get_db_session),
) -> PasswordResetValidateResponse:
    """Validate a setup/reset token without consuming it."""
    try:
        tok, user = await setup_token_service.validate_token(db, token)
        return PasswordResetValidateResponse(email=user.email, valid=True, purpose=tok.purpose)
    except ValueError:
        return PasswordResetValidateResponse(email="", valid=False, purpose=None)


@router.post("/setup/complete", response_model=UserResponse)
@limiter.limit(settings.register_rate_limit)
async def complete_setup(
    request: Request,
    response: Response,
    body: PasswordResetCompletePayload,
    db: AsyncSession = Depends(get_db_session),
) -> UserResponse:
    """Set the user's password via a valid setup/reset token and log them in."""
    try:
        user = await setup_token_service.consume_token(db, body.token, body.password)
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from None

    # BYOK: a setup/reset flow does not have the OLD password in scope,
    # so the wrapped DEK is unrecoverable. Mark it orphaned so the UI
    # prompts the user to re-enrol their API key on next chat. No-op
    # for users without an active enrollment (the common path,
    # including every first-time-setup admin).
    byok_session_service.orphan_dek(user)

    new_session = await session_service.create_session(
        db,
        user_id=user.id,
        user_agent=request.headers.get("user-agent"),
        ip=request.client.host if request.client else None,
    )
    set_session_cookies(
        response,
        session_cookie_value=new_session.cookie_value,
        csrf_token=new_session.csrf_token,
    )

    balance = await balance_service.get_balance(db, user.id)
    return UserResponse(
        id=user.id,
        email=user.email,
        display_name=user.display_name,
        background=user.role.name if user.role_id and user.role else None,
        is_admin=user.is_admin,
        created_at=None,
        balance_usd=balance.balance_usd if balance else None,
        balance_tokens=balance.balance_tokens if balance else None,
    )


@router.post("/password/change", status_code=status.HTTP_200_OK)
async def change_password(
    body: PasswordChangePayload,
    current_user: AuthUser = Depends(require_auth),
    db: AsyncSession = Depends(get_db_session),
) -> dict[str, str]:
    """Change your own password after providing the current one."""
    from app.services.auth_service import get_user_by_id

    user = await get_user_by_id(db, current_user.id)
    if user is None or not user.is_active:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Not authenticated")

    if not user.password_hash or not verify_password(body.current_password, user.password_hash):
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Current password is incorrect")

    # BYOK: re-wrap the user's DEK under a KEK derived from the new
    # password before we replace the password hash. If the wrapped DEK
    # is unreadable (corrupt blob, AAD mismatch), fall through to
    # marking the BYOK row orphaned — the password change should still
    # succeed; the user will simply have to re-enrol their API key.
    try:
        byok_session_service.rewrap_dek_on_password_change(user, body.current_password, body.new_password)
    except BYOKDecryptionError:
        logger.exception("BYOK rewrap failed during password change; orphaning DEK (user=%s)", user.id)
        byok_session_service.orphan_dek(user)

    user.password_hash = hash_password(body.new_password)
    return {"message": "Password updated"}
