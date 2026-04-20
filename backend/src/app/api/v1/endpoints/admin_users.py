"""Admin endpoints for managing users (list, promote/demote, deactivate, assign role, reset password)."""

from __future__ import annotations

import contextlib
import uuid

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import AuthUser, require_admin
from app.db.session import get_db_session
from app.schemas.admin_user import (
    AdminBalanceResponse,
    AdminBalanceTopUpRequest,
    AdminUserDetail,
    AdminUserListResponse,
    AdminUserResetPasswordResponse,
    AdminUserUpdateRequest,
)
from app.services import admin_service, balance_service, role_service, setup_token_service
from app.services.email_service import send_setup_email

router = APIRouter()


def _detail_from(user, aggregates) -> AdminUserDetail:  # type: ignore[no-untyped-def]
    base = AdminUserDetail.model_validate(user)
    agg = aggregates.get(user.id)
    if agg is None:
        return base
    return base.model_copy(
        update={
            "total_cost_usd": agg.total_cost_usd,
            "total_markup_cost_usd": agg.total_markup_cost_usd,
            "total_tokens": agg.total_tokens,
            "conversation_count": agg.conversation_count,
            "last_conversation_at": agg.last_conversation_at,
            "feedback_count": agg.feedback_count,
            "open_experiments": agg.open_experiments,
            "avg_runs_per_experiment": agg.avg_runs_per_experiment,
            "balance_usd": agg.balance_usd,
            "balance_tokens": agg.balance_tokens,
            "signup_status": agg.signup_status,
            "disclaimers_accepted": agg.disclaimers_accepted,
        }
    )


@router.get("", response_model=AdminUserListResponse)
async def list_users(
    page: int = Query(1, ge=1),
    page_size: int = Query(50, ge=1, le=100),
    search: str | None = Query(None),
    admins_only: bool = Query(False),
    _admin: AuthUser = Depends(require_admin),
    db: AsyncSession = Depends(get_db_session),
) -> AdminUserListResponse:
    users, aggregates, total = await admin_service.list_users(
        db, page=page, page_size=page_size, search=search, admins_only=admins_only
    )
    return AdminUserListResponse(
        users=[_detail_from(u, aggregates) for u in users],
        total=total,
        page=page,
        page_size=page_size,
    )


@router.patch("/{user_id}", response_model=AdminUserDetail)
async def update_user(
    user_id: uuid.UUID,
    body: AdminUserUpdateRequest,
    current_admin: AuthUser = Depends(require_admin),
    db: AsyncSession = Depends(get_db_session),
) -> AdminUserDetail:
    from app.services.auth_service import get_user_by_id

    user = await get_user_by_id(db, user_id)
    if user is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="User not found")

    # Self-demotion guard at the API layer too, so the error message is
    # nicer than the generic "last admin" from admin_service.
    if user.id == current_admin.id and body.is_admin is False:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="You can't demote yourself")

    try:
        if body.is_admin is not None:
            await admin_service.set_admin(db, user, body.is_admin)
        if body.is_active is not None:
            await admin_service.set_active(db, user, body.is_active)
        if body.clear_role:
            await admin_service.set_role(db, user, None)
        elif body.role_id is not None:
            role = await role_service.get_role(db, body.role_id)
            if role is None:
                raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Role not found")
            await admin_service.set_role(db, user, role.id)
        if body.display_name is not None:
            user.display_name = body.display_name
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from None

    await db.refresh(user)
    return AdminUserDetail.model_validate(user)


@router.post("/{user_id}/reset-password", response_model=AdminUserResetPasswordResponse)
async def reset_user_password(
    user_id: uuid.UUID,
    _admin: AuthUser = Depends(require_admin),
    db: AsyncSession = Depends(get_db_session),
) -> AdminUserResetPasswordResponse:
    """Issue a one-time password-reset link for a user and email it.

    The reset URL is also returned in the response so the admin can copy
    it out-of-band when SMTP isn't configured.
    """
    from app.services.auth_service import get_user_by_id

    user = await get_user_by_id(db, user_id)
    if user is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="User not found")

    token = await setup_token_service.issue_token(db, user, setup_token_service.RESET)
    url = await setup_token_service.build_setup_url(token)

    with contextlib.suppress(Exception):
        await send_setup_email(user.email, url, is_first_time=False)

    return AdminUserResetPasswordResponse(
        message=f"Reset link issued for {user.email}",
        url=url,
    )


@router.post("/{user_id}/balance/topup", response_model=AdminBalanceResponse)
async def top_up_user_balance(
    user_id: uuid.UUID,
    body: AdminBalanceTopUpRequest,
    current_admin: AuthUser = Depends(require_admin),
    db: AsyncSession = Depends(get_db_session),
) -> AdminBalanceResponse:
    """Credit ``usd`` and/or ``tokens`` to a user's balance. Audited as an admin_event."""
    from app.services.auth_service import get_user_by_id

    user = await get_user_by_id(db, user_id)
    if user is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="User not found")

    balance = await balance_service.top_up(
        db,
        user_id=user.id,
        usd=body.usd,
        tokens=body.tokens,
        actor_email=current_admin.email,
    )
    return AdminBalanceResponse(
        user_id=user.id,
        balance_usd=balance.balance_usd,
        balance_tokens=balance.balance_tokens,
    )
