"""Unit tests for ``app.services.admin_event_service``.

Uses the session-scoped Postgres engine + transactional ``db_session``
fixture from ``conftest.py``.
"""

from __future__ import annotations

import time
import uuid

import pytest
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.admin_event import AdminEvent  # noqa: F401 — register table
from app.services import admin_event_service


async def test_start_event_inserts_in_progress(db_session: AsyncSession) -> None:
    event_id = await admin_event_service.start_event(
        db_session,
        event_type="postgres_backup",
        source="cron@vps01",
        payload={"s3_key": "postgres/daily/.../doe.dump"},
    )

    row = (await db_session.execute(select(AdminEvent).where(AdminEvent.id == event_id))).scalar_one()
    assert row.status == "in_progress"
    assert row.event_type == "postgres_backup"
    assert row.source == "cron@vps01"
    assert row.payload == {"s3_key": "postgres/daily/.../doe.dump"}
    assert row.started_at is not None
    assert row.completed_at is None
    assert row.duration_ms is None


async def test_finish_event_success_fills_timing_and_merges_payload(db_session: AsyncSession) -> None:
    event_id = await admin_event_service.start_event(
        db_session,
        event_type="postgres_backup",
        source="cron@vps01",
        payload={"s3_key": "k1", "retention_class": "daily"},
    )

    time.sleep(0.01)

    await admin_event_service.finish_event(
        db_session,
        event_id,
        status="success",
        payload_merge={"size_bytes": 12345, "sha256": "abc"},
    )

    row = (await db_session.execute(select(AdminEvent).where(AdminEvent.id == event_id))).scalar_one()
    assert row.status == "success"
    assert row.error_message is None
    assert row.completed_at is not None
    assert row.duration_ms is not None and row.duration_ms >= 0
    # Shallow merge preserves existing keys and adds new ones.
    assert row.payload == {
        "s3_key": "k1",
        "retention_class": "daily",
        "size_bytes": 12345,
        "sha256": "abc",
    }


async def test_finish_event_failed_records_error_message(db_session: AsyncSession) -> None:
    event_id = await admin_event_service.start_event(
        db_session,
        event_type="postgres_backup",
        source="cron@vps01",
    )

    await admin_event_service.finish_event(
        db_session,
        event_id,
        status="failed",
        error_message="pg_dump timed out after 1800s",
    )

    row = (await db_session.execute(select(AdminEvent).where(AdminEvent.id == event_id))).scalar_one()
    assert row.status == "failed"
    assert row.error_message == "pg_dump timed out after 1800s"


async def test_finish_event_rejects_unknown_status(db_session: AsyncSession) -> None:
    event_id = await admin_event_service.start_event(
        db_session,
        event_type="postgres_backup",
        source="cron@vps01",
    )
    with pytest.raises(ValueError, match="success|failed"):
        await admin_event_service.finish_event(db_session, event_id, status="done")


async def test_finish_event_rejects_unknown_id(db_session: AsyncSession) -> None:
    with pytest.raises(ValueError, match="not found"):
        await admin_event_service.finish_event(db_session, uuid.uuid4(), status="success")


async def test_log_snapshot_inserts_info_row(db_session: AsyncSession) -> None:
    event_id = await admin_event_service.log_snapshot(
        db_session,
        event_type="user_count_snapshot",
        source="app",
        payload={"total_users": 42, "active_users": 40},
    )

    row = (await db_session.execute(select(AdminEvent).where(AdminEvent.id == event_id))).scalar_one()
    assert row.status == "info"
    assert row.event_type == "user_count_snapshot"
    assert row.payload == {"total_users": 42, "active_users": 40}
    assert row.started_at is None
    assert row.completed_at is None
