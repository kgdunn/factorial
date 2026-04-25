"""Tests for the /api/v1/experiments/uploads endpoints."""

from __future__ import annotations

import io
import uuid
from datetime import UTC, datetime
from typing import Any
from unittest.mock import AsyncMock, patch

import pytest
from httpx import ASGITransport, AsyncClient
from openpyxl import Workbook

from app.api.v1.endpoints.uploads import DESIGN_TYPE_UPLOADED
from app.db.session import get_db_session
from app.main import app
from app.schemas.uploads import (
    ClarifyingQuestion,
    ParsedDesignPayload,
    UploadFactor,
    UploadResponse,
)

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _xlsx_bytes(rows: list[list[object]]) -> bytes:
    wb = Workbook()
    ws = wb.active
    for row in rows:
        ws.append(row)
    buf = io.BytesIO()
    wb.save(buf)
    return buf.getvalue()


def _basic_parsed() -> ParsedDesignPayload:
    return ParsedDesignPayload(
        orientation="rows",
        factors=[
            UploadFactor(name="Temperature", type="continuous", low=50, high=80),
            UploadFactor(name="Pressure", type="continuous", low=1.0, high=2.0),
        ],
        responses=[UploadResponse(name="Yield", goal="maximize")],
        design_actual=[
            {"Temperature": 50, "Pressure": 1.0, "Yield": 72.3},
            {"Temperature": 80, "Pressure": 2.0, "Yield": 88.4},
        ],
        results_data=[
            {"Temperature": 50, "Pressure": 1.0, "Yield": 72.3},
            {"Temperature": 80, "Pressure": 2.0, "Yield": 88.4},
        ],
    )


class _FakeExperiment:
    """Mimic the Experiment ORM row for the create / get / finalize flow."""

    def __init__(self, **kwargs: Any) -> None:
        self.id = kwargs.get("id", uuid.uuid4())
        self.user_id = kwargs.get("user_id", uuid.uuid4())
        self.name = kwargs.get("name", "Imported design")
        self.status = kwargs.get("status", "draft")
        self.design_type = kwargs.get("design_type", DESIGN_TYPE_UPLOADED)
        self.factors = kwargs.get("factors")
        self.design_data = kwargs.get("design_data")
        self.results_data = kwargs.get("results_data")
        self.evaluation_data = kwargs.get("evaluation_data")
        self.conversation_id = kwargs.get("conversation_id")
        self.created_at = kwargs.get("created_at", datetime.now(UTC))
        self.updated_at = kwargs.get("updated_at", datetime.now(UTC))


class _RecordingSession:
    """Minimal AsyncSession stand-in.

    ``add`` captures the ORM object and assigns required defaults so
    serialisation works; ``flush`` is a no-op coroutine.
    """

    def __init__(self) -> None:
        self.added: list[Any] = []

    def add(self, obj: Any) -> None:
        if not getattr(obj, "id", None):
            obj.id = uuid.uuid4()
        if not getattr(obj, "created_at", None):
            obj.created_at = datetime.now(UTC)
        if not getattr(obj, "updated_at", None):
            obj.updated_at = datetime.now(UTC)
        self.added.append(obj)

    async def flush(self) -> None:  # pragma: no cover — trivial
        return None


def _override_db(session: _RecordingSession):
    async def _gen():
        yield session

    app.dependency_overrides[get_db_session] = _gen


def _clear_db_override() -> None:
    app.dependency_overrides.pop(get_db_session, None)


# ---------------------------------------------------------------------------
# POST /experiments/uploads
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_post_upload_returns_parsed_when_claude_is_confident() -> None:
    session = _RecordingSession()
    _override_db(session)
    try:
        with patch(
            "app.api.v1.endpoints.uploads.discover_structure",
            new=AsyncMock(return_value=_basic_parsed()),
        ):
            transport = ASGITransport(app=app)
            async with AsyncClient(transport=transport, base_url="http://test") as ac:
                resp = await ac.post(
                    "/api/v1/experiments/uploads",
                    files={
                        "file": (
                            "design.xlsx",
                            _xlsx_bytes(
                                [
                                    ["Temperature", "Pressure", "Yield"],
                                    [50, 1.0, 72.3],
                                ]
                            ),
                            "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                        )
                    },
                )
        assert resp.status_code == 200
        body = resp.json()
        assert body["status"] == "parsed"
        assert body["parsed"]["orientation"] == "rows"
        assert body["questions"] is None
        assert body["raw_preview"][0] == ["Temperature", "Pressure", "Yield"]
        assert len(session.added) == 1
        exp = session.added[0]
        assert exp.status == "draft"
        assert exp.design_type == DESIGN_TYPE_UPLOADED
        assert exp.factors and len(exp.factors) == 2
    finally:
        _clear_db_override()


@pytest.mark.asyncio
async def test_post_upload_returns_questions_when_ambiguous() -> None:
    session = _RecordingSession()
    _override_db(session)
    questions = [ClarifyingQuestion(id="q1", question="Is `yield` a factor or an outcome?")]
    try:
        with patch(
            "app.api.v1.endpoints.uploads.discover_structure",
            new=AsyncMock(return_value=questions),
        ):
            transport = ASGITransport(app=app)
            async with AsyncClient(transport=transport, base_url="http://test") as ac:
                resp = await ac.post(
                    "/api/v1/experiments/uploads",
                    files={
                        "file": (
                            "ambiguous.xlsx",
                            _xlsx_bytes([["yield", "x"], [1, 2]]),
                            "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                        )
                    },
                )
        assert resp.status_code == 200
        body = resp.json()
        assert body["status"] == "needs_clarification"
        assert body["parsed"] is None
        assert len(body["questions"]) == 1
        assert body["questions"][0]["id"] == "q1"
        # The draft was still persisted so the user can answer asynchronously.
        assert len(session.added) == 1
        assert session.added[0].factors is None
    finally:
        _clear_db_override()


@pytest.mark.asyncio
async def test_post_upload_rejects_unsupported_extension() -> None:
    session = _RecordingSession()
    _override_db(session)
    try:
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as ac:
            resp = await ac.post(
                "/api/v1/experiments/uploads",
                files={"file": ("design.txt", b"a,b\n1,2\n", "text/plain")},
            )
        assert resp.status_code == 400
        assert "extension" in resp.json()["detail"].lower()
        assert session.added == []
    finally:
        _clear_db_override()


# ---------------------------------------------------------------------------
# POST /experiments/uploads/{id}/answers
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_post_answers_re_runs_claude_with_prior_qa() -> None:
    session = _RecordingSession()
    _override_db(session)
    upload_id = uuid.uuid4()
    fake_exp = _FakeExperiment(
        id=upload_id,
        design_data={
            "design_type": DESIGN_TYPE_UPLOADED,
            "upload_source": {
                "filename": "ambiguous.xlsx",
                "raw_preview": [["yield", "x"], [1, 2]],
                "questions": [{"id": "q1", "question": "Is `yield` a factor or an outcome?"}],
                "answers": {},
            },
        },
    )
    discover_mock = AsyncMock(return_value=_basic_parsed())
    try:
        with (
            patch(
                "app.api.v1.endpoints.uploads.experiment_service.get_experiment",
                new=AsyncMock(return_value=fake_exp),
            ),
            patch(
                "app.api.v1.endpoints.uploads.discover_structure",
                new=discover_mock,
            ),
        ):
            transport = ASGITransport(app=app)
            async with AsyncClient(transport=transport, base_url="http://test") as ac:
                resp = await ac.post(
                    f"/api/v1/experiments/uploads/{upload_id}/answers",
                    json={"answers": {"q1": "outcome"}},
                )
        assert resp.status_code == 200
        body = resp.json()
        assert body["status"] == "parsed"
        assert body["parsed"]["orientation"] == "rows"
        # The mock should have been called with prior_questions and prior_answers.
        kwargs = discover_mock.call_args.kwargs
        assert kwargs["prior_answers"] == {"q1": "outcome"}
        assert len(kwargs["prior_questions"]) == 1
        assert kwargs["prior_questions"][0].id == "q1"
        # The persisted experiment should now carry factors.
        assert fake_exp.factors and len(fake_exp.factors) == 2
        assert fake_exp.design_data["upload_source"]["answers"] == {"q1": "outcome"}
    finally:
        _clear_db_override()


@pytest.mark.asyncio
async def test_post_answers_404_when_upload_unknown() -> None:
    session = _RecordingSession()
    _override_db(session)
    try:
        with patch(
            "app.api.v1.endpoints.uploads.experiment_service.get_experiment",
            new=AsyncMock(return_value=None),
        ):
            transport = ASGITransport(app=app)
            async with AsyncClient(transport=transport, base_url="http://test") as ac:
                resp = await ac.post(
                    f"/api/v1/experiments/uploads/{uuid.uuid4()}/answers",
                    json={"answers": {"q1": "outcome"}},
                )
        assert resp.status_code == 404
    finally:
        _clear_db_override()


# ---------------------------------------------------------------------------
# POST /experiments/uploads/{id}/finalize
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_post_finalize_writes_user_edits_and_promotes_status() -> None:
    session = _RecordingSession()
    _override_db(session)
    upload_id = uuid.uuid4()
    fake_exp = _FakeExperiment(
        id=upload_id,
        design_data={
            "design_type": DESIGN_TYPE_UPLOADED,
            "upload_source": {
                "filename": "design.xlsx",
                "raw_preview": [["Temperature", "Yield"], [50, 72]],
                "questions": [],
                "answers": {},
            },
        },
        factors=[{"name": "Temperature"}],
    )
    user_edited = _basic_parsed().model_copy(
        update={
            "factors": [
                UploadFactor(name="Temperature_renamed", type="continuous", low=50, high=80),
            ]
        }
    )
    try:
        with patch(
            "app.api.v1.endpoints.uploads.experiment_service.get_experiment",
            new=AsyncMock(return_value=fake_exp),
        ):
            transport = ASGITransport(app=app)
            async with AsyncClient(transport=transport, base_url="http://test") as ac:
                resp = await ac.post(
                    f"/api/v1/experiments/uploads/{upload_id}/finalize",
                    json={
                        "name": "First batch",
                        "parsed": user_edited.model_dump(),
                    },
                )
        assert resp.status_code == 200
        body = resp.json()
        assert body["name"] == "First batch"
        # User's renamed factor wins, not Claude's original "Temperature".
        assert fake_exp.factors == [
            {
                "name": "Temperature_renamed",
                "type": "continuous",
                "low": 50.0,
                "high": 80.0,
                "levels": None,
                "units": None,
            }
        ]
        # results_data was non-empty -> status promoted.
        assert fake_exp.status == "active"
        assert fake_exp.design_data["n_factors"] == 1
        assert fake_exp.design_data["upload_source"]["filename"] == "design.xlsx"
    finally:
        _clear_db_override()


@pytest.mark.asyncio
async def test_post_finalize_keeps_draft_when_no_results() -> None:
    session = _RecordingSession()
    _override_db(session)
    upload_id = uuid.uuid4()
    fake_exp = _FakeExperiment(
        id=upload_id,
        status="draft",
        design_data={
            "design_type": DESIGN_TYPE_UPLOADED,
            "upload_source": {
                "filename": "design.xlsx",
                "raw_preview": [["Temperature"], [50]],
                "questions": [],
                "answers": {},
            },
        },
    )
    no_results = _basic_parsed().model_copy(update={"results_data": []})
    try:
        with patch(
            "app.api.v1.endpoints.uploads.experiment_service.get_experiment",
            new=AsyncMock(return_value=fake_exp),
        ):
            transport = ASGITransport(app=app)
            async with AsyncClient(transport=transport, base_url="http://test") as ac:
                resp = await ac.post(
                    f"/api/v1/experiments/uploads/{upload_id}/finalize",
                    json={"parsed": no_results.model_dump()},
                )
        assert resp.status_code == 200
        assert fake_exp.status == "draft"
    finally:
        _clear_db_override()
