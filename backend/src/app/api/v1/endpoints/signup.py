"""Signup request endpoints: public submission, invite registration, and admin management."""

from __future__ import annotations

import contextlib
import logging
import uuid

from fastapi import APIRouter, Depends, HTTPException, Query, Request, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import AuthUser, require_admin
from app.api.rate_limit import limiter
from app.config import settings
from app.db.session import get_db_session
from app.schemas.auth import TokenResponse
from app.schemas.signup import (
    InviteRegisterRequest,
    InviteValidateResponse,
    SignupApproveRequest,
    SignupDetail,
    SignupListResponse,
    SignupRejectRequest,
    SignupSubmitRequest,
    SignupSubmitResponse,
)
from app.services.admin_service import list_admin_emails
from app.services.auth_service import create_access_token, create_refresh_token
from app.services.email_service import send_admin_notification, send_invite_email, send_signup_confirmation
from app.services.signup_service import (
    approve_signup,
    complete_registration,
    create_signup,
    list_signups,
    reject_signup,
    validate_invite_token,
)

logger = logging.getLogger(__name__)

router = APIRouter()


# ---------------------------------------------------------------------------
# Public endpoints
# ---------------------------------------------------------------------------


@router.post("/request", response_model=SignupSubmitResponse, status_code=status.HTTP_201_CREATED)
@limiter.limit(settings.register_rate_limit)
async def submit_signup(
    request: Request,
    body: SignupSubmitRequest,
    db: AsyncSession = Depends(get_db_session),
) -> SignupSubmitResponse:
    """Submit a signup request for admin review."""
    try:
        await create_signup(db, email=body.email, use_case=body.use_case, requested_role=body.requested_role)
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(exc)) from None

    admin_emails = await list_admin_emails(db)

    # Fire-and-forget emails (don't fail the request if email fails)
    with contextlib.suppress(Exception):
        await send_admin_notification(body.email, body.use_case, admin_emails)
    with contextlib.suppress(Exception):
        await send_signup_confirmation(body.email, body.use_case)

    return SignupSubmitResponse(
        message="Your signup request has been received. We'll email you when your account is ready.",
    )


@router.get("/invite/validate", response_model=InviteValidateResponse)
async def validate_invite(
    token: str = Query(...),
    db: AsyncSession = Depends(get_db_session),
) -> InviteValidateResponse:
    """Validate an invite token without consuming it."""
    try:
        signup = await validate_invite_token(db, token)
        return InviteValidateResponse(email=signup.email, valid=True)
    except ValueError:
        return InviteValidateResponse(email="", valid=False)


@router.post("/invite/register", response_model=TokenResponse, status_code=status.HTTP_201_CREATED)
@limiter.limit(settings.register_rate_limit)
async def register_with_invite(
    request: Request,
    body: InviteRegisterRequest,
    db: AsyncSession = Depends(get_db_session),
) -> TokenResponse:
    """Complete registration using an invite token."""
    try:
        user = await complete_registration(
            db,
            token=body.token,
            password=body.password,
            display_name=body.display_name,
        )
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from None

    return TokenResponse(
        access_token=create_access_token(user.id, user.email),
        refresh_token=create_refresh_token(user.id),
    )


# ---------------------------------------------------------------------------
# Admin endpoints
# ---------------------------------------------------------------------------


@router.get("/admin/list", response_model=SignupListResponse)
async def admin_list_signups(
    status_filter: str | None = Query(None, alias="status"),
    page: int = Query(1, ge=1),
    page_size: int = Query(50, ge=1, le=100),
    _admin: AuthUser = Depends(require_admin),
    db: AsyncSession = Depends(get_db_session),
) -> SignupListResponse:
    """List signup requests (admin only)."""
    signups, total = await list_signups(db, status_filter=status_filter, page=page, page_size=page_size)
    return SignupListResponse(
        signups=[SignupDetail.model_validate(s) for s in signups],
        total=total,
        page=page,
        page_size=page_size,
    )


@router.post("/admin/{signup_id}/approve", status_code=status.HTTP_200_OK)
async def admin_approve_signup(
    signup_id: uuid.UUID,
    body: SignupApproveRequest | None = None,
    _admin: AuthUser = Depends(require_admin),
    db: AsyncSession = Depends(get_db_session),
) -> dict[str, str]:
    """Approve a signup, optionally assigning or creating a role, and send the invite."""
    body = body or SignupApproveRequest()
    try:
        signup = await approve_signup(
            db,
            signup_id,
            role_id=body.role_id,
            new_role_name=body.new_role.name if body.new_role else None,
            new_role_description=body.new_role.description if body.new_role else None,
        )
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from None

    with contextlib.suppress(Exception):
        await send_invite_email(signup.email, signup.invite_token)

    return {"message": f"Signup approved and invite sent to {signup.email}"}


@router.post("/admin/{signup_id}/reject", status_code=status.HTTP_200_OK)
async def admin_reject_signup(
    signup_id: uuid.UUID,
    body: SignupRejectRequest | None = None,
    _admin: AuthUser = Depends(require_admin),
    db: AsyncSession = Depends(get_db_session),
) -> dict[str, str]:
    """Reject a signup request (admin only)."""
    note = body.note if body else None
    try:
        await reject_signup(db, signup_id, note=note)
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from None

    return {"message": "Signup rejected"}
