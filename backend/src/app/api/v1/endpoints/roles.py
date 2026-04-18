"""Roles endpoints.

``GET /roles`` is public so the signup form can populate its dropdown.
All mutations require admin.
"""

from __future__ import annotations

import uuid

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import AuthUser, require_admin
from app.db.session import get_db_session
from app.schemas.role import (
    RoleCreateRequest,
    RoleListResponse,
    RoleResponse,
    RoleUpdateRequest,
)
from app.services import role_service

router = APIRouter()


@router.get("", response_model=RoleListResponse)
async def list_roles(db: AsyncSession = Depends(get_db_session)) -> RoleListResponse:
    """Return every role. Public: the signup form needs it."""
    roles = await role_service.list_roles(db)
    return RoleListResponse(roles=[RoleResponse.model_validate(r) for r in roles])


@router.post("", response_model=RoleResponse, status_code=status.HTTP_201_CREATED)
async def create_role(
    body: RoleCreateRequest,
    _admin: AuthUser = Depends(require_admin),
    db: AsyncSession = Depends(get_db_session),
) -> RoleResponse:
    try:
        role = await role_service.create_role(db, body.name, body.description)
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from None
    return RoleResponse.model_validate(role)


@router.patch("/{role_id}", response_model=RoleResponse)
async def update_role(
    role_id: uuid.UUID,
    body: RoleUpdateRequest,
    _admin: AuthUser = Depends(require_admin),
    db: AsyncSession = Depends(get_db_session),
) -> RoleResponse:
    role = await role_service.get_role(db, role_id)
    if role is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Role not found")
    await role_service.update_role(db, role, body.description)
    return RoleResponse.model_validate(role)


@router.delete("/{role_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_role(
    role_id: uuid.UUID,
    _admin: AuthUser = Depends(require_admin),
    db: AsyncSession = Depends(get_db_session),
) -> None:
    role = await role_service.get_role(db, role_id)
    if role is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Role not found")
    try:
        await role_service.delete_role(db, role)
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from None
