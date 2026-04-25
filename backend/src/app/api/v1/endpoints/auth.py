"""Authentication endpoints: login, logout, /me, sessions list."""

from __future__ import annotations

import uuid
from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException, Request, Response, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.auth_cookies import clear_session_cookies, set_session_cookies
from app.api.deps import SERVICE_USER_ID, AuthUser, require_auth
from app.api.rate_limit import limiter
from app.config import settings
from app.db.session import get_db_session
from app.schemas.auth import (
    LoginRequest,
    RegisterRequest,
    SessionResponse,
    UserResponse,
)
from app.services import balance_service, session_service
from app.services.auth_service import authenticate_user, record_login_activity

router = APIRouter()


def _client_ip(request: Request) -> str | None:
    """Return the caller's IP, honouring a single ``X-Forwarded-For`` hop.

    We only trust the left-most XFF entry when a reverse proxy (Caddy/nginx)
    is in front. In dev there is no proxy, so ``request.client.host`` is used.
    """
    fwd = request.headers.get("x-forwarded-for")
    if fwd:
        first = fwd.split(",")[0].strip()
        if first:
            return first
    return request.client.host if request.client else None


def _user_agent(request: Request) -> str | None:
    return request.headers.get("user-agent")


@router.post("/register", status_code=status.HTTP_403_FORBIDDEN)
@limiter.limit(settings.register_rate_limit)
async def register(
    request: Request,
    body: RegisterRequest,
) -> dict[str, str]:
    """Direct registration is disabled — users must be invited."""
    raise HTTPException(
        status_code=status.HTTP_403_FORBIDDEN,
        detail="Registration is by invite only. Please submit a signup request first.",
    )


@router.post("/login", response_model=UserResponse)
@limiter.limit(settings.auth_rate_limit)
async def login(
    request: Request,
    response: Response,
    body: LoginRequest,
    db: AsyncSession = Depends(get_db_session),
) -> UserResponse:
    """Authenticate with email/password, mint a session, set cookies."""
    user = await authenticate_user(db, email=body.email, password=body.password)
    if not user:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid email or password",
        )

    ip = _client_ip(request)
    await record_login_activity(db, user, ip=ip, timezone=body.timezone)
    new_session = await session_service.create_session(
        db,
        user_id=user.id,
        user_agent=_user_agent(request),
        ip=ip,
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


@router.post("/logout", status_code=status.HTTP_204_NO_CONTENT)
async def logout(
    response: Response,
    current_user: AuthUser = Depends(require_auth),
    db: AsyncSession = Depends(get_db_session),
) -> Response:
    """Revoke the current session and clear cookies. Idempotent."""
    if current_user.session_id is not None:
        await session_service.revoke_session(db, current_user.session_id)
    clear_session_cookies(response)
    response.status_code = status.HTTP_204_NO_CONTENT
    return response


@router.post("/logout-all", status_code=status.HTTP_204_NO_CONTENT)
async def logout_all(
    response: Response,
    current_user: AuthUser = Depends(require_auth),
    db: AsyncSession = Depends(get_db_session),
) -> Response:
    """Revoke every active session for this user; clear current cookie."""
    if current_user.family_id is not None:
        # Revoke by user_id rather than family_id alone — a user may have
        # multiple families if they ever logged in from cookie-cleared
        # devices, and "sign out everywhere" should mean exactly that.
        await session_service.revoke_family(db, current_user.family_id)
    # Also catch any sessions in other families belonging to this user.
    sessions = await session_service.list_user_sessions(db, current_user.id)
    for s in sessions:
        await session_service.revoke_session(db, s.id)
    clear_session_cookies(response)
    response.status_code = status.HTTP_204_NO_CONTENT
    return response


@router.get("/me", response_model=UserResponse)
async def get_me(
    current_user: AuthUser = Depends(require_auth),
    db: AsyncSession = Depends(get_db_session),
) -> UserResponse:
    """Get the current authenticated user's profile."""
    balance_usd = None
    balance_tokens = None
    if current_user.id != SERVICE_USER_ID:
        balance = await balance_service.get_balance(db, current_user.id)
        if balance is not None:
            balance_usd = balance.balance_usd
            balance_tokens = balance.balance_tokens

    return UserResponse(
        id=current_user.id,
        email=current_user.email,
        display_name=current_user.display_name,
        background=current_user.background,
        created_at=None,
        is_admin=current_user.is_admin,
        balance_usd=balance_usd,
        balance_tokens=balance_tokens,
    )


@router.get("/sessions", response_model=list[SessionResponse])
async def list_sessions(
    current_user: AuthUser = Depends(require_auth),
    db: AsyncSession = Depends(get_db_session),
) -> list[SessionResponse]:
    """List the current user's active sessions, newest-used first."""
    rows = await session_service.list_user_sessions(db, current_user.id)
    return [
        SessionResponse(
            public_id=row.public_id,
            created_at=_as_dt(row.created_at),
            last_used_at=_as_dt(row.last_used_at),
            user_agent=row.user_agent,
            ip=row.ip,
            is_current=(row.id == current_user.session_id),
        )
        for row in rows
    ]


@router.delete("/sessions/{public_id}", status_code=status.HTTP_204_NO_CONTENT)
async def revoke_session(
    public_id: uuid.UUID,
    current_user: AuthUser = Depends(require_auth),
    db: AsyncSession = Depends(get_db_session),
) -> Response:
    """Revoke one of the current user's sessions by its public id."""
    revoked = await session_service.revoke_by_public_id(
        db,
        user_id=current_user.id,
        public_id=public_id,
    )
    if not revoked:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Session not found",
        )
    return Response(status_code=status.HTTP_204_NO_CONTENT)


def _as_dt(value: object) -> datetime:
    """Coerce an ORM-returned timestamp to ``datetime`` for the schema."""
    if isinstance(value, datetime):
        return value
    return datetime.fromisoformat(str(value))
