"""Unit tests for ``admin_event_service.list_events``.

Kept separate from ``test_admin_event_service.py`` (which covers the
write helpers) so each file stays focused.
"""

from __future__ import annotations

import datetime as dt

from sqlalchemy.ext.asyncio import AsyncSession

from app.models.admin_event import AdminEvent
from app.services import admin_event_service


async def _seed(
    session: AsyncSession,
    *,
    event_type: str,
    status: str,
    created_at: dt.datetime,
) -> AdminEvent:
    row = AdminEvent(
        event_type=event_type,
        status=status,
        source="test",
        payload={},
        created_at=created_at,
        updated_at=created_at,
    )
    session.add(row)
    await session.flush()
    return row


async def test_list_events_orders_newest_first_and_paginates(db_session: AsyncSession) -> None:
    base = dt.datetime(2026, 4, 1, 0, 0, 0, tzinfo=dt.UTC)
    for i in range(25):
        await _seed(
            db_session,
            event_type="postgres_backup",
            status="success",
            created_at=base + dt.timedelta(minutes=i),
        )

    page1, total = await admin_event_service.list_events(db_session, page=1, page_size=10)
    assert total == 25
    assert len(page1) == 10
    # Newest first: index 24 sits on top, then 23, ...
    assert [e.created_at for e in page1] == sorted((e.created_at for e in page1), reverse=True)

    page3, total3 = await admin_event_service.list_events(db_session, page=3, page_size=10)
    assert total3 == 25
    assert len(page3) == 5


async def test_list_events_filters_by_event_type(db_session: AsyncSession) -> None:
    base = dt.datetime(2026, 4, 1, 0, 0, 0, tzinfo=dt.UTC)
    for i in range(5):
        await _seed(
            db_session,
            event_type="postgres_backup",
            status="success",
            created_at=base + dt.timedelta(minutes=i),
        )
    for i in range(3):
        await _seed(
            db_session,
            event_type="restore_drill",
            status="success",
            created_at=base + dt.timedelta(hours=1, minutes=i),
        )

    rows, total = await admin_event_service.list_events(db_session, event_type="postgres_backup")
    assert total == 5
    assert all(r.event_type == "postgres_backup" for r in rows)


async def test_list_events_filters_by_status(db_session: AsyncSession) -> None:
    base = dt.datetime(2026, 4, 1, 0, 0, 0, tzinfo=dt.UTC)
    for i in range(4):
        await _seed(
            db_session,
            event_type="postgres_backup",
            status="success",
            created_at=base + dt.timedelta(minutes=i),
        )
    for i in range(2):
        await _seed(
            db_session,
            event_type="postgres_backup",
            status="failed",
            created_at=base + dt.timedelta(hours=1, minutes=i),
        )

    rows, total = await admin_event_service.list_events(db_session, status="failed")
    assert total == 2
    assert all(r.status == "failed" for r in rows)


async def test_list_events_combined_filter(db_session: AsyncSession) -> None:
    base = dt.datetime(2026, 4, 1, 0, 0, 0, tzinfo=dt.UTC)
    await _seed(db_session, event_type="postgres_backup", status="failed", created_at=base)
    await _seed(db_session, event_type="postgres_backup", status="success", created_at=base + dt.timedelta(minutes=1))
    await _seed(db_session, event_type="restore_drill", status="failed", created_at=base + dt.timedelta(minutes=2))

    rows, total = await admin_event_service.list_events(db_session, event_type="postgres_backup", status="failed")
    assert total == 1
    assert rows[0].event_type == "postgres_backup"
    assert rows[0].status == "failed"


async def test_list_events_empty_returns_zero_total(db_session: AsyncSession) -> None:
    rows, total = await admin_event_service.list_events(db_session)
    assert rows == []
    assert total == 0
