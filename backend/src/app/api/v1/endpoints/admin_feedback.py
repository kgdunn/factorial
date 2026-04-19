"""Admin endpoints for the user feedback inbox."""

from __future__ import annotations

import uuid

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, Query, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import AuthUser, require_admin
from app.db.session import async_session_factory, get_db_session
from app.models.user import User
from app.models.user_feedback import UserFeedback
from app.schemas.feedback import (
    FeedbackListResponse,
    FeedbackMarkRepliedRequest,
    FeedbackReplyRequest,
)
from app.services import feedback_service
from app.services.auth_service import get_user_by_id
from app.services.feedback_emails import notify_user_of_reply

router = APIRouter()


async def _deliver_reply(feedback_id: uuid.UUID, admin_id: uuid.UUID, body: str) -> None:
    async with async_session_factory() as db:
        feedback = await db.get(UserFeedback, feedback_id)
        admin_user = await db.get(User, admin_id)
        if feedback is None or admin_user is None:
            return
        user = await db.get(User, feedback.user_id)
        if user is None:
            return
        await notify_user_of_reply(feedback, user, admin_user, body)


@router.get("", response_model=FeedbackListResponse)
async def list_feedback(
    page: int = Query(1, ge=1),
    page_size: int = Query(50, ge=1, le=100),
    replied: bool | None = Query(None),
    _admin: AuthUser = Depends(require_admin),
    db: AsyncSession = Depends(get_db_session),
) -> FeedbackListResponse:
    items, total = await feedback_service.list_feedback(db, page=page, page_size=page_size, replied=replied)
    return FeedbackListResponse(items=items, total=total, page=page, page_size=page_size)


@router.post("/{feedback_id}/reply", status_code=status.HTTP_200_OK)
async def reply_to_feedback(
    feedback_id: uuid.UUID,
    body: FeedbackReplyRequest,
    background_tasks: BackgroundTasks,
    admin: AuthUser = Depends(require_admin),
    db: AsyncSession = Depends(get_db_session),
) -> dict[str, str]:
    feedback = await feedback_service.get_feedback(db, feedback_id)
    if feedback is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Feedback not found")
    admin_user = await get_user_by_id(db, admin.id)
    if admin_user is None:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Admin not found")
    await feedback_service.record_admin_reply(db, admin_user=admin_user, feedback=feedback, body=body.body)
    await db.commit()
    background_tasks.add_task(_deliver_reply, feedback.id, admin_user.id, body.body)
    return {"status": "sent"}


@router.patch("/{feedback_id}", status_code=status.HTTP_200_OK)
async def mark_replied(
    feedback_id: uuid.UUID,
    body: FeedbackMarkRepliedRequest,
    admin: AuthUser = Depends(require_admin),
    db: AsyncSession = Depends(get_db_session),
) -> dict[str, str]:
    feedback = await feedback_service.get_feedback(db, feedback_id)
    if feedback is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Feedback not found")
    admin_user = await get_user_by_id(db, admin.id)
    if admin_user is None:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Admin not found")
    await feedback_service.set_replied_flag(db, admin_user=admin_user, feedback=feedback, replied=body.replied)
    await db.commit()
    return {"status": "ok"}
