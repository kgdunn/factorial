"""User-facing feedback endpoints.

``POST /api/v1/feedback`` records a submission and fires email
notifications to the submitter and every active admin in a background
task so the HTTP round-trip isn't held up by SMTP.

``GET /api/v1/feedback/{id}/screenshot`` returns the PNG bytes for a row
owned by the caller or for admins.
"""

from __future__ import annotations

import uuid

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, Request, Response, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import AuthUser, require_auth
from app.api.rate_limit import limiter
from app.config import settings
from app.db.session import async_session_factory, get_db_session
from app.models.user import User
from app.models.user_feedback import UserFeedback
from app.schemas.feedback import FeedbackSubmitRequest, FeedbackSubmitResponse
from app.services import admin_service, feedback_service
from app.services.auth_service import get_user_by_id
from app.services.feedback_emails import (
    notify_admins_of_submission,
    notify_user_of_submission,
)
from app.services.feedback_service import (
    ScreenshotInvalidError,
    ScreenshotTooLargeError,
)

try:
    from importlib.metadata import version as _pkg_version

    _APP_VERSION: str | None = _pkg_version("agentic-doe")
except Exception:  # noqa: BLE001
    _APP_VERSION = None


router = APIRouter()


async def _deliver_notifications(feedback_id: uuid.UUID, user_id: uuid.UUID) -> None:
    """Background task: load the feedback row and fan out emails."""
    async with async_session_factory() as db:
        feedback = await db.get(UserFeedback, feedback_id)
        user = await db.get(User, user_id)
        if feedback is None or user is None:
            return
        admin_emails = await admin_service.list_admin_emails(db)
        await notify_user_of_submission(feedback, user)
        await notify_admins_of_submission(feedback, user, admin_emails)


@router.post("", response_model=FeedbackSubmitResponse, status_code=status.HTTP_201_CREATED)
@limiter.limit(settings.feedback_rate_limit)
async def submit_feedback(
    request: Request,  # noqa: ARG001  required by slowapi
    body: FeedbackSubmitRequest,
    background_tasks: BackgroundTasks,
    current_user: AuthUser = Depends(require_auth),
    db: AsyncSession = Depends(get_db_session),
) -> FeedbackSubmitResponse:
    user = await get_user_by_id(db, current_user.id)
    if user is None:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="User not found")
    try:
        feedback = await feedback_service.create_feedback(
            db,
            user=user,
            payload=body,
            app_version=_APP_VERSION,
        )
    except ScreenshotTooLargeError as exc:
        raise HTTPException(
            status_code=status.HTTP_413_REQUEST_ENTITY_TOO_LARGE,
            detail=str(exc),
        ) from exc
    except ScreenshotInvalidError as exc:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(exc),
        ) from exc
    await db.commit()
    await db.refresh(feedback)
    background_tasks.add_task(_deliver_notifications, feedback.id, user.id)
    return FeedbackSubmitResponse(id=feedback.id, created_at=feedback.created_at)


@router.get("/{feedback_id}/screenshot")
async def get_screenshot(
    feedback_id: uuid.UUID,
    current_user: AuthUser = Depends(require_auth),
    db: AsyncSession = Depends(get_db_session),
) -> Response:
    feedback = await feedback_service.get_feedback(db, feedback_id)
    if feedback is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Feedback not found")
    if feedback.user_id != current_user.id and not current_user.is_admin:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Feedback not found")
    payload = await feedback_service.get_feedback_screenshot(db, feedback_id)
    if payload is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="No screenshot attached")
    data, mime = payload
    return Response(content=data, media_type=mime)
