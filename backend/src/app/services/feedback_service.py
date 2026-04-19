"""CRUD helpers for the ``user_feedback`` table."""

from __future__ import annotations

import base64
import binascii
import datetime as dt
import uuid

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import aliased

from app.models.user import User
from app.models.user_feedback import UserFeedback
from app.schemas.feedback import (
    MAX_SCREENSHOT_BYTES,
    FeedbackRow,
    FeedbackSubmitRequest,
)


class ScreenshotTooLargeError(ValueError):
    """Decoded screenshot exceeds :data:`MAX_SCREENSHOT_BYTES`."""


class ScreenshotInvalidError(ValueError):
    """Base64 payload did not decode."""


def _decode_screenshot(payload: str | None) -> bytes | None:
    if payload is None or payload == "":
        return None
    stripped = payload.split(",", 1)[-1] if payload.startswith("data:") else payload
    try:
        raw = base64.b64decode(stripped, validate=True)
    except (binascii.Error, ValueError) as exc:
        raise ScreenshotInvalidError("Screenshot is not valid base64") from exc  # noqa: TRY003
    if len(raw) > MAX_SCREENSHOT_BYTES:
        raise ScreenshotTooLargeError(  # noqa: TRY003
            f"Screenshot is {len(raw)} bytes; maximum is {MAX_SCREENSHOT_BYTES}"
        )
    return raw


async def create_feedback(
    db: AsyncSession,
    *,
    user: User,
    payload: FeedbackSubmitRequest,
    app_version: str | None,
) -> UserFeedback:
    screenshot = _decode_screenshot(payload.screenshot_png_b64)
    row = UserFeedback(
        user_id=user.id,
        topic=payload.topic,
        message=payload.message,
        page_url=payload.page_url,
        user_agent=payload.user_agent,
        viewport=payload.viewport,
        app_version=app_version,
        screenshot_png=screenshot,
        screenshot_mime="image/png" if screenshot else None,
    )
    db.add(row)
    await db.flush()
    return row


async def get_feedback(db: AsyncSession, feedback_id: uuid.UUID) -> UserFeedback | None:
    return await db.get(UserFeedback, feedback_id)


async def get_feedback_screenshot(db: AsyncSession, feedback_id: uuid.UUID) -> tuple[bytes, str] | None:
    result = await db.execute(
        select(UserFeedback.screenshot_png, UserFeedback.screenshot_mime).where(UserFeedback.id == feedback_id)
    )
    row = result.first()
    if row is None or row.screenshot_png is None:
        return None
    return bytes(row.screenshot_png), row.screenshot_mime or "image/png"


async def list_feedback(
    db: AsyncSession,
    *,
    page: int = 1,
    page_size: int = 50,
    replied: bool | None = None,
) -> tuple[list[FeedbackRow], int]:
    submitter = aliased(User)
    replier = aliased(User)
    base = (
        select(
            UserFeedback.id,
            UserFeedback.user_id,
            submitter.email.label("user_email"),
            submitter.display_name.label("user_display_name"),
            UserFeedback.topic,
            UserFeedback.message,
            UserFeedback.page_url,
            UserFeedback.user_agent,
            UserFeedback.viewport,
            UserFeedback.app_version,
            (UserFeedback.screenshot_png.is_not(None)).label("has_screenshot"),
            UserFeedback.replied_at,
            UserFeedback.replied_by_user_id,
            replier.email.label("replied_by_email"),
            UserFeedback.reply_body,
            UserFeedback.created_at,
        )
        .join(submitter, submitter.id == UserFeedback.user_id)
        .outerjoin(replier, replier.id == UserFeedback.replied_by_user_id)
    )
    count_q = select(func.count()).select_from(UserFeedback)
    if replied is True:
        base = base.where(UserFeedback.replied_at.is_not(None))
        count_q = count_q.where(UserFeedback.replied_at.is_not(None))
    elif replied is False:
        base = base.where(UserFeedback.replied_at.is_(None))
        count_q = count_q.where(UserFeedback.replied_at.is_(None))

    base = base.order_by(UserFeedback.created_at.desc()).offset((page - 1) * page_size).limit(page_size)
    result = await db.execute(base)
    items = [FeedbackRow(**row._mapping) for row in result.all()]
    total = (await db.execute(count_q)).scalar_one()
    return items, total


async def record_admin_reply(
    db: AsyncSession,
    *,
    admin_user: User,
    feedback: UserFeedback,
    body: str,
) -> UserFeedback:
    feedback.reply_body = body
    feedback.replied_at = dt.datetime.now(dt.UTC)
    feedback.replied_by_user_id = admin_user.id
    await db.flush()
    return feedback


async def set_replied_flag(
    db: AsyncSession,
    *,
    admin_user: User,
    feedback: UserFeedback,
    replied: bool,
) -> UserFeedback:
    if replied:
        feedback.replied_at = dt.datetime.now(dt.UTC)
        feedback.replied_by_user_id = admin_user.id
    else:
        feedback.replied_at = None
        feedback.replied_by_user_id = None
        feedback.reply_body = None
    await db.flush()
    return feedback
