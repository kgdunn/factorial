"""Pydantic schemas for experiment CRUD endpoints."""

from __future__ import annotations

import uuid
from datetime import datetime
from enum import StrEnum
from typing import Any

from pydantic import BaseModel, Field


class ExperimentStatus(StrEnum):
    """Lifecycle status of an experiment."""

    draft = "draft"
    active = "active"
    completed = "completed"
    archived = "archived"


# ---------------------------------------------------------------------------
# Response schemas
# ---------------------------------------------------------------------------


class ExperimentSummary(BaseModel):
    """Lightweight experiment representation for list views."""

    id: uuid.UUID
    name: str
    status: ExperimentStatus
    design_type: str | None = None
    n_runs: int | None = None
    n_factors: int | None = None
    conversation_id: uuid.UUID | None = None
    created_at: datetime
    updated_at: datetime

    model_config = {"from_attributes": True}


class ExperimentDetail(ExperimentSummary):
    """Full experiment with design data, results, and evaluation."""

    factors: list[dict[str, Any]] | None = None
    design_data: dict[str, Any] | None = None
    results_data: list[dict[str, Any]] | None = None
    evaluation_data: dict[str, Any] | None = None


class ExperimentListResponse(BaseModel):
    """Paginated list of experiments."""

    experiments: list[ExperimentSummary]
    total: int
    page: int
    page_size: int


# ---------------------------------------------------------------------------
# Request schemas
# ---------------------------------------------------------------------------


class ExperimentUpdate(BaseModel):
    """PATCH /experiments/{id} request body."""

    name: str | None = Field(None, min_length=1, max_length=255)
    status: ExperimentStatus | None = None


class ResultsEntry(BaseModel):
    """POST /experiments/{id}/results request body.

    Each item in ``results`` must include ``run_index`` (int) and may
    include one or more response columns with numeric values.

    Two optional per-row metadata keys are also recognised:

    * ``notes`` (``str``): free-form observation about that data point.
    * ``included`` (``bool``, default ``true`` when omitted): whether
      the row should participate in downstream analysis.  ``false``
      flags the point as an excluded outlier; the response value is
      still preserved so the user can revert later.

    Rows are stored as-is in ``experiments.results_data`` and merged on
    ``run_index`` (see ``experiment_service.add_results``), so any extra
    keys round-trip transparently.
    """

    results: list[dict[str, Any]] = Field(
        ...,
        min_length=1,
        description=(
            "Array of result objects. Each must have 'run_index' (int); response "
            "columns and the optional 'notes' (str) / 'included' (bool, default true) "
            "metadata keys are all merged on run_index."
        ),
    )


class ResultsResponse(BaseModel):
    """Response for results endpoints."""

    experiment_id: uuid.UUID
    results_data: list[dict[str, Any]] | None = None
    n_results_entered: int


class EvaluateRequest(BaseModel):
    """POST /experiments/{id}/evaluate request body.

    All fields are optional. When ``metrics`` is omitted the endpoint
    requests a comprehensive default set covering resolution, aliasing,
    efficiency, VIF, condition number, and power.
    """

    assumed_sigma: float | None = Field(
        None,
        gt=0,
        description="Residual standard deviation assumed for power analysis.",
    )
    effect_size: float | None = Field(
        None,
        description="Minimum practical effect size used for power analysis.",
    )
    alpha: float | None = Field(
        None,
        gt=0,
        lt=1,
        description="Type-I error rate used for power calculation.",
    )
    metrics: list[str] | None = Field(
        None,
        description="Subset of evaluate_design metrics; defaults to a comprehensive set.",
    )
