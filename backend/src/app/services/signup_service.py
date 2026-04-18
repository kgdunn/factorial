"""Signup service: create, list, approve/reject requests, and invite-based registration."""

from __future__ import annotations

import secrets
import uuid
from datetime import UTC, datetime, timedelta

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from app.models.role import Role
from app.models.signup_request import SignupRequest
from app.models.user import User
from app.services import role_service
from app.services.auth_service import hash_password


async def create_signup(
    db: AsyncSession,
    email: str,
    use_case: str,
    requested_role: str | None = None,
) -> SignupRequest:
    """Create a new pending signup request.

    Raises
    ------
    ValueError
        If the email already has a pending or approved signup, or is already registered.
    """
    result = await db.execute(
        select(SignupRequest).where(
            SignupRequest.email == email,
            SignupRequest.status.in_(["pending", "approved"]),
        )
    )
    if result.scalar_one_or_none():
        raise ValueError("A signup request for this email is already pending or approved")  # noqa: TRY003

    # Also check if the email is already a registered user
    result = await db.execute(select(User).where(User.email == email))
    if result.scalar_one_or_none():
        raise ValueError("This email is already registered")  # noqa: TRY003

    signup = SignupRequest(email=email, use_case=use_case, requested_role=requested_role)
    db.add(signup)
    await db.flush()
    return signup


async def list_signups(
    db: AsyncSession,
    status_filter: str | None = None,
    page: int = 1,
    page_size: int = 50,
) -> tuple[list[SignupRequest], int]:
    """Return a paginated list of signup requests with an optional status filter."""
    query = select(SignupRequest)
    count_query = select(func.count()).select_from(SignupRequest)

    if status_filter:
        query = query.where(SignupRequest.status == status_filter)
        count_query = count_query.where(SignupRequest.status == status_filter)

    query = query.order_by(SignupRequest.created_at.desc())
    query = query.offset((page - 1) * page_size).limit(page_size)

    result = await db.execute(query)
    signups = list(result.scalars().all())

    count_result = await db.execute(count_query)
    total = count_result.scalar_one()

    return signups, total


async def approve_signup(
    db: AsyncSession,
    signup_id: uuid.UUID,
    role_id: uuid.UUID | None = None,
    new_role_name: str | None = None,
    new_role_description: str | None = None,
) -> SignupRequest:
    """Approve a signup request, optionally assigning or creating a role.

    The caller passes exactly one of: ``role_id`` (use existing role),
    ``new_role_name`` (create a new role as part of approval), or
    neither (approve without a role).

    Raises
    ------
    ValueError
        Signup not found, not pending, or role arguments invalid.
    """
    if role_id is not None and new_role_name is not None:
        raise ValueError("Pass either role_id or new_role, not both")  # noqa: TRY003

    signup = await db.get(SignupRequest, signup_id)
    if not signup:
        raise ValueError("Signup request not found")  # noqa: TRY003
    if signup.status != "pending":
        raise ValueError(f"Signup is already {signup.status}")  # noqa: TRY003

    resolved_role: Role | None = None
    if new_role_name is not None:
        resolved_role = await role_service.create_role(db, new_role_name, new_role_description)
    elif role_id is not None:
        resolved_role = await role_service.get_role(db, role_id)
        if resolved_role is None:
            raise ValueError("Role not found")  # noqa: TRY003

    signup.status = "approved"
    signup.invite_token = secrets.token_urlsafe(32)
    signup.invite_expires_at = datetime.now(UTC) + timedelta(hours=settings.invite_token_expire_hours)
    if resolved_role is not None:
        signup.role_id = resolved_role.id
    await db.flush()
    return signup


async def reject_signup(
    db: AsyncSession,
    signup_id: uuid.UUID,
    note: str | None = None,
) -> SignupRequest:
    """Reject a signup request.

    Raises
    ------
    ValueError
        If the signup is not found or not in pending status.
    """
    signup = await db.get(SignupRequest, signup_id)
    if not signup:
        raise ValueError("Signup request not found")  # noqa: TRY003
    if signup.status != "pending":
        raise ValueError(f"Signup is already {signup.status}")  # noqa: TRY003

    signup.status = "rejected"
    if note:
        signup.admin_note = note
    await db.flush()
    return signup


async def validate_invite_token(db: AsyncSession, token: str) -> SignupRequest:
    """Validate an invite token and return the signup request.

    Raises
    ------
    ValueError
        If the token is invalid, expired, or already used.
    """
    result = await db.execute(select(SignupRequest).where(SignupRequest.invite_token == token))
    signup = result.scalar_one_or_none()
    if not signup:
        raise ValueError("Invalid invite token")  # noqa: TRY003
    if signup.status != "approved":
        raise ValueError("This invite has already been used or is no longer valid")  # noqa: TRY003
    if signup.invite_expires_at and datetime.now(UTC) > signup.invite_expires_at.replace(tzinfo=UTC):
        raise ValueError("This invite has expired")  # noqa: TRY003
    return signup


async def complete_registration(
    db: AsyncSession,
    token: str,
    password: str,
    display_name: str | None = None,
) -> User:
    """Complete registration using an invite token.

    Validates the token, creates a User whose ``role_id`` is copied from
    the signup request, and marks the signup as registered.

    Raises
    ------
    ValueError
        If the token is invalid/expired or the email is already registered.
    """
    signup = await validate_invite_token(db, token)

    # Check if user already exists (defensive)
    result = await db.execute(select(User).where(User.email == signup.email))
    if result.scalar_one_or_none():
        raise ValueError("This email is already registered")  # noqa: TRY003

    user = User(
        email=signup.email,
        password_hash=hash_password(password),
        display_name=display_name,
        role_id=signup.role_id,
    )
    db.add(user)

    signup.status = "registered"
    await db.flush()
    return user
