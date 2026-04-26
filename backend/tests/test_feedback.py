"""Tests for the user feedback feature.

Schema-level validation runs with plain Pydantic. Service-level tests
use the session-scoped Postgres ``db_session`` fixture from
``conftest.py``.
"""

from __future__ import annotations

import base64

import pytest
from pydantic import ValidationError
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.user import User
from app.models.user_feedback import UserFeedback
from app.schemas.feedback import (
    FeedbackReplyRequest,
    FeedbackSubmitRequest,
)
from app.services import feedback_service


def _make_payload(**overrides: object) -> dict[str, object]:
    body: dict[str, object] = {
        "topic": "incorrect_response",
        "message": "The answer was wrong in the previous turn.",
        "page_url": "http://localhost:5173/chat/123",
    }
    body.update(overrides)
    return body


class TestSubmitRequestValidation:
    def test_happy_path(self) -> None:
        body = FeedbackSubmitRequest.model_validate(_make_payload())
        assert body.topic == "incorrect_response"
        assert body.screenshot_png_b64 is None

    def test_rejects_unknown_topic(self) -> None:
        with pytest.raises(ValidationError):
            FeedbackSubmitRequest.model_validate(_make_payload(topic="rants"))

    def test_rejects_short_message(self) -> None:
        with pytest.raises(ValidationError):
            FeedbackSubmitRequest.model_validate(_make_payload(message="too short"))

    def test_rejects_message_over_cap(self) -> None:
        with pytest.raises(ValidationError):
            FeedbackSubmitRequest.model_validate(_make_payload(message="x" * 5_001))


class TestReplyRequestValidation:
    def test_happy_path(self) -> None:
        body = FeedbackReplyRequest.model_validate({"body": "Thanks, this is fixed now."})
        assert body.body.startswith("Thanks")

    def test_rejects_short_body(self) -> None:
        with pytest.raises(ValidationError):
            FeedbackReplyRequest.model_validate({"body": "hi"})


async def _seed_user(db: AsyncSession, *, email: str = "user@example.com", is_admin: bool = False) -> User:
    user = User(
        email=email,
        password_hash="",
        display_name="Test User",
        is_admin=is_admin,
        is_active=True,
    )
    db.add(user)
    await db.flush()
    return user


async def test_create_feedback_without_screenshot(db_session: AsyncSession) -> None:
    user = await _seed_user(db_session)
    payload = FeedbackSubmitRequest.model_validate(_make_payload())

    row = await feedback_service.create_feedback(db_session, user=user, payload=payload, app_version="0.15.0")

    assert row.user_id == user.id
    assert row.topic == "incorrect_response"
    assert row.screenshot_png is None
    assert row.screenshot_mime is None
    assert row.app_version == "0.15.0"


async def test_create_feedback_with_screenshot(db_session: AsyncSession) -> None:
    user = await _seed_user(db_session)
    image = b"\x89PNG\r\n\x1a\n" + b"fake bytes"
    payload = FeedbackSubmitRequest.model_validate(
        _make_payload(screenshot_png_b64=base64.b64encode(image).decode("ascii"))
    )

    row = await feedback_service.create_feedback(db_session, user=user, payload=payload, app_version=None)

    assert bytes(row.screenshot_png) == image
    assert row.screenshot_mime == "image/png"


async def test_create_feedback_rejects_oversize_screenshot(db_session: AsyncSession) -> None:
    user = await _seed_user(db_session)
    too_big = b"x" * (2 * 1024 * 1024 + 1)
    payload = FeedbackSubmitRequest.model_validate(
        _make_payload(screenshot_png_b64=base64.b64encode(too_big).decode("ascii"))
    )

    with pytest.raises(feedback_service.ScreenshotTooLargeError):
        await feedback_service.create_feedback(db_session, user=user, payload=payload, app_version=None)


async def test_create_feedback_rejects_invalid_base64(db_session: AsyncSession) -> None:
    user = await _seed_user(db_session)
    payload = FeedbackSubmitRequest.model_validate(_make_payload(screenshot_png_b64="this is not base64!!!"))

    with pytest.raises(feedback_service.ScreenshotInvalidError):
        await feedback_service.create_feedback(db_session, user=user, payload=payload, app_version=None)


async def test_list_feedback_and_replied_filter(db_session: AsyncSession) -> None:
    user = await _seed_user(db_session)
    admin = await _seed_user(db_session, email="admin@example.com", is_admin=True)

    for i in range(3):
        await feedback_service.create_feedback(
            db_session,
            user=user,
            payload=FeedbackSubmitRequest.model_validate(_make_payload(message=f"feedback {i} is long enough to pass")),
            app_version=None,
        )

    rows = (await db_session.execute(select(UserFeedback))).scalars().all()
    await feedback_service.record_admin_reply(db_session, admin_user=admin, feedback=rows[0], body="resolved, thanks")

    all_items, total = await feedback_service.list_feedback(db_session)
    assert total == 3
    assert len(all_items) == 3
    unreplied, unreplied_total = await feedback_service.list_feedback(db_session, replied=False)
    assert unreplied_total == 2
    assert all(item.replied_at is None for item in unreplied)
    replied, replied_total = await feedback_service.list_feedback(db_session, replied=True)
    assert replied_total == 1
    assert replied[0].replied_by_email == "admin@example.com"
    assert replied[0].reply_body == "resolved, thanks"


async def test_set_replied_flag_clears_reply_body(db_session: AsyncSession) -> None:
    user = await _seed_user(db_session)
    admin = await _seed_user(db_session, email="admin@example.com", is_admin=True)
    row = await feedback_service.create_feedback(
        db_session,
        user=user,
        payload=FeedbackSubmitRequest.model_validate(_make_payload()),
        app_version=None,
    )

    await feedback_service.set_replied_flag(db_session, admin_user=admin, feedback=row, replied=True)
    assert row.replied_at is not None
    assert row.replied_by_user_id == admin.id

    await feedback_service.set_replied_flag(db_session, admin_user=admin, feedback=row, replied=False)
    assert row.replied_at is None
    assert row.replied_by_user_id is None
    assert row.reply_body is None
