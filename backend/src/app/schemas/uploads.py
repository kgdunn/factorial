"""Pydantic schemas for the DOE experiment upload flow.

The upload flow turns a user-supplied Excel/CSV file into a draft
:class:`app.models.experiment.Experiment` via Claude. Three endpoints
share these shapes:

* ``POST /experiments/uploads``                       → :class:`UploadParseResponse`
* ``POST /experiments/uploads/{id}/answers``          → :class:`UploadParseResponse`
* ``POST /experiments/uploads/{id}/finalize``         → ``ExperimentDetail`` (see ``schemas.experiments``)
"""

from __future__ import annotations

import uuid
from typing import Any, Literal

from pydantic import BaseModel, Field

# Hard upper bound on the number of clarifying questions Claude is allowed to
# return in a single round-trip. Larger lists almost always indicate a
# pathological prompt response and degrade UX. Trim server-side.
MAX_CLARIFYING_QUESTIONS = 5

FactorType = Literal["continuous", "categorical", "mixture"]
ResponseGoal = Literal["maximize", "minimize", "target"]
Orientation = Literal["rows", "columns"]
UploadStatus = Literal["needs_clarification", "parsed"]


class UploadFactor(BaseModel):
    """A factor as detected by Claude from the uploaded matrix.

    Field names mirror :class:`process_improve.experiments.factor.Factor`
    so the payload validates downstream without remapping.
    """

    name: str = Field(..., min_length=1, max_length=255)
    type: FactorType = "continuous"
    low: float | None = None
    high: float | None = None
    levels: list[Any] | None = None
    units: str | None = None


class UploadResponse(BaseModel):
    """A response (outcome) column as detected by Claude."""

    name: str = Field(..., min_length=1, max_length=255)
    goal: ResponseGoal | None = None
    units: str | None = None


class ClarifyingQuestion(BaseModel):
    """One question Claude wants the user to answer before committing.

    ``id`` is Claude-assigned (e.g. ``"q1"``) and used to thread the
    answer back on the second round-trip.
    """

    id: str = Field(..., min_length=1, max_length=32)
    question: str = Field(..., min_length=1, max_length=1_000)
    options: list[str] | None = Field(
        None,
        description="Multiple-choice options. None means free-text answer.",
    )
    column_ref: str | None = Field(
        None,
        description="Column header or coordinate the question is about.",
    )


class ParsedDesignPayload(BaseModel):
    """Final parsed structure once Claude is confident."""

    orientation: Orientation
    factors: list[UploadFactor]
    responses: list[UploadResponse] = Field(default_factory=list)
    design_actual: list[dict[str, Any]] = Field(
        default_factory=list,
        description="One dict per run, keyed by factor (and response) name.",
    )
    results_data: list[dict[str, Any]] = Field(
        default_factory=list,
        description="Subset of design_actual rows where response columns were filled in.",
    )


class UploadParseResponse(BaseModel):
    """Response from the initial upload and the answers submission.

    Either ``parsed`` is populated (status == ``"parsed"``) or
    ``questions`` is populated (status == ``"needs_clarification"``).
    Never both. ``raw_preview`` always echoes the matrix the server
    extracted so the UI can render the original file.
    """

    upload_id: uuid.UUID
    status: UploadStatus
    parsed: ParsedDesignPayload | None = None
    questions: list[ClarifyingQuestion] | None = None
    raw_preview: list[list[Any]]


class UploadAnswerRequest(BaseModel):
    """User's answers to the clarifying questions, keyed by question id."""

    answers: dict[str, str] = Field(..., min_length=1)


class UploadFinalizeRequest(BaseModel):
    """User-confirmed structure that overwrites Claude's draft on save."""

    name: str | None = Field(None, min_length=1, max_length=255)
    parsed: ParsedDesignPayload
