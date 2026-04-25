"""REST endpoints for the DOE experiment upload flow.

Three routes, all mounted under ``/api/v1/experiments/uploads``:

* ``POST   ""``                                  — accept the file, parse, ask Claude, persist a draft
* ``POST   "/{upload_id}/answers"``              — second round-trip with the user's clarifying answers
* ``POST   "/{upload_id}/finalize"``             — write the user-confirmed structure and surface as a normal Experiment
"""

from __future__ import annotations

import logging
import uuid
from typing import Any

from fastapi import APIRouter, Depends, File, HTTPException, UploadFile
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import AuthUser, require_auth
from app.db.session import get_db_session
from app.models.experiment import Experiment
from app.schemas.experiments import ExperimentDetail
from app.schemas.uploads import (
    ClarifyingQuestion,
    ParsedDesignPayload,
    UploadAnswerRequest,
    UploadFinalizeRequest,
    UploadParseResponse,
)
from app.services import experiment_service
from app.services.upload_claude_service import UploadClaudeError, discover_structure
from app.services.upload_parsing_service import UploadValidationError, parse_upload

logger = logging.getLogger(__name__)

router = APIRouter()

DESIGN_TYPE_UPLOADED = "uploaded"


# ---------------------------------------------------------------------------
# POST /experiments/uploads
# ---------------------------------------------------------------------------


@router.post("", response_model=UploadParseResponse)
async def create_upload(
    file: UploadFile = File(...),
    db: AsyncSession = Depends(get_db_session),
    current_user: AuthUser = Depends(require_auth),
) -> UploadParseResponse:
    """Accept an Excel/CSV file and run the first Claude pass.

    Always creates a draft Experiment so the upload survives a refresh
    or a reload of the wizard. The ``upload_id`` is the experiment's
    primary key.
    """

    raw = await file.read()

    try:
        parsed_file = parse_upload(file.filename or "", raw)
    except UploadValidationError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    try:
        result = await discover_structure(parsed_file.rows)
    except UploadClaudeError as exc:
        raise HTTPException(status_code=502, detail=str(exc)) from exc

    if isinstance(result, ParsedDesignPayload):
        experiment = await _persist_initial_draft(
            db,
            user_id=current_user.id,
            filename=file.filename or "",
            raw_preview=parsed_file.rows,
            questions=None,
            parsed=result,
        )
        return UploadParseResponse(
            upload_id=experiment.id,
            status="parsed",
            parsed=result,
            questions=None,
            raw_preview=parsed_file.rows,
        )

    # Otherwise: clarifying questions.
    experiment = await _persist_initial_draft(
        db,
        user_id=current_user.id,
        filename=file.filename or "",
        raw_preview=parsed_file.rows,
        questions=result,
        parsed=None,
    )
    return UploadParseResponse(
        upload_id=experiment.id,
        status="needs_clarification",
        parsed=None,
        questions=result,
        raw_preview=parsed_file.rows,
    )


# ---------------------------------------------------------------------------
# POST /experiments/uploads/{upload_id}/answers
# ---------------------------------------------------------------------------


@router.post("/{upload_id}/answers", response_model=UploadParseResponse)
async def submit_answers(
    upload_id: uuid.UUID,
    body: UploadAnswerRequest,
    db: AsyncSession = Depends(get_db_session),
    current_user: AuthUser = Depends(require_auth),
) -> UploadParseResponse:
    """Re-run Claude with the user's answers attached to the prompt."""

    experiment = await experiment_service.get_experiment(db, upload_id, current_user.id)
    if not experiment:
        raise HTTPException(status_code=404, detail="Upload not found.")

    upload_source = _read_upload_source(experiment)
    raw_preview = upload_source.get("raw_preview") or []
    prior_questions = [ClarifyingQuestion.model_validate(q) for q in upload_source.get("questions") or []]

    try:
        result = await discover_structure(
            raw_preview,
            prior_questions=prior_questions,
            prior_answers=body.answers,
        )
    except UploadClaudeError as exc:
        raise HTTPException(status_code=502, detail=str(exc)) from exc

    if not isinstance(result, ParsedDesignPayload):
        # Defensive: Claude asked again despite being told not to.
        raise HTTPException(
            status_code=502,
            detail="Claude could not commit to a structure even with answers. Try uploading again.",
        )

    upload_source["answers"] = body.answers
    experiment.factors = [f.model_dump() for f in result.factors]
    experiment.design_data = _build_design_data(upload_source, result)
    await db.flush()

    return UploadParseResponse(
        upload_id=experiment.id,
        status="parsed",
        parsed=result,
        questions=None,
        raw_preview=raw_preview,
    )


# ---------------------------------------------------------------------------
# POST /experiments/uploads/{upload_id}/finalize
# ---------------------------------------------------------------------------


@router.post("/{upload_id}/finalize", response_model=ExperimentDetail)
async def finalize_upload(
    upload_id: uuid.UUID,
    body: UploadFinalizeRequest,
    db: AsyncSession = Depends(get_db_session),
    current_user: AuthUser = Depends(require_auth),
) -> ExperimentDetail:
    """Persist the user-confirmed structure as a normal Experiment.

    The user's edits in ``body.parsed`` overwrite Claude's draft so
    inline corrections in the wizard always win.
    """

    experiment = await experiment_service.get_experiment(db, upload_id, current_user.id)
    if not experiment:
        raise HTTPException(status_code=404, detail="Upload not found.")

    upload_source = _read_upload_source(experiment)
    if body.name:
        experiment.name = body.name
    experiment.factors = [f.model_dump() for f in body.parsed.factors]
    experiment.design_data = _build_design_data(upload_source, body.parsed)
    experiment.results_data = list(body.parsed.results_data) or None
    if body.parsed.results_data:
        experiment.status = "active"
    await db.flush()

    return ExperimentDetail.model_validate(experiment, from_attributes=True)


# ---------------------------------------------------------------------------
# Internals
# ---------------------------------------------------------------------------


async def _persist_initial_draft(
    db: AsyncSession,
    *,
    user_id: uuid.UUID,
    filename: str,
    raw_preview: list[list[Any]],
    questions: list[ClarifyingQuestion] | None,
    parsed: ParsedDesignPayload | None,
) -> Experiment:
    upload_source: dict[str, Any] = {
        "filename": filename,
        "raw_preview": raw_preview,
        "questions": [q.model_dump() for q in questions] if questions else [],
        "answers": {},
    }
    experiment = Experiment(
        user_id=user_id,
        name=filename or "Imported design",
        status="draft",
        design_type=DESIGN_TYPE_UPLOADED,
        factors=[f.model_dump() for f in parsed.factors] if parsed else None,
        design_data=_build_design_data(upload_source, parsed),
    )
    db.add(experiment)
    await db.flush()
    return experiment


def _build_design_data(
    upload_source: dict[str, Any],
    parsed: ParsedDesignPayload | None,
) -> dict[str, Any]:
    payload: dict[str, Any] = {
        "design_type": DESIGN_TYPE_UPLOADED,
        "upload_source": upload_source,
    }
    if parsed:
        payload.update(
            {
                "orientation": parsed.orientation,
                "design_actual": list(parsed.design_actual),
                "responses": [r.model_dump() for r in parsed.responses],
                "n_runs": len(parsed.design_actual),
                "n_factors": len(parsed.factors),
            }
        )
    return payload


def _read_upload_source(experiment: Experiment) -> dict[str, Any]:
    data = experiment.design_data or {}
    source = data.get("upload_source")
    if not isinstance(source, dict):
        raise HTTPException(
            status_code=409,
            detail="This experiment was not created by the upload flow.",
        )
    return dict(source)
