"""CRUD endpoints for experiments."""

from __future__ import annotations

import uuid
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import AuthUser, require_auth
from app.db.session import get_db_session
from app.schemas.experiments import (
    ExperimentDetail,
    ExperimentListResponse,
    ExperimentSummary,
    ExperimentUpdate,
    ResultsEntry,
    ResultsResponse,
)
from app.services import experiment_service

router = APIRouter()


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _summary_from_model(exp: Any) -> ExperimentSummary:
    """Build an ``ExperimentSummary`` from an ORM Experiment instance."""
    design_data = exp.design_data or {}
    return ExperimentSummary(
        id=exp.id,
        name=exp.name,
        status=exp.status,
        design_type=exp.design_type,
        n_runs=design_data.get("n_runs"),
        n_factors=design_data.get("n_factors"),
        conversation_id=exp.conversation_id,
        created_at=exp.created_at,
        updated_at=exp.updated_at,
    )


def _detail_from_model(exp: Any) -> ExperimentDetail:
    """Build an ``ExperimentDetail`` from an ORM Experiment instance."""
    design_data = exp.design_data or {}
    return ExperimentDetail(
        id=exp.id,
        name=exp.name,
        status=exp.status,
        design_type=exp.design_type,
        n_runs=design_data.get("n_runs"),
        n_factors=design_data.get("n_factors"),
        conversation_id=exp.conversation_id,
        created_at=exp.created_at,
        updated_at=exp.updated_at,
        factors=exp.factors,
        design_data=exp.design_data,
        results_data=exp.results_data,
    )


# ---------------------------------------------------------------------------
# Endpoints
# ---------------------------------------------------------------------------


@router.get("")
async def list_experiments(
    status: str | None = Query(None, description="Filter by status (draft, active, completed, archived)"),
    page: int = Query(1, ge=1, description="Page number"),
    page_size: int = Query(20, ge=1, le=100, description="Items per page"),
    db: AsyncSession = Depends(get_db_session),
    current_user: AuthUser = Depends(require_auth),
) -> ExperimentListResponse:
    """List experiments with optional status filter and pagination."""
    experiments, total = await experiment_service.list_experiments(
        db,
        user_id=current_user.id,
        is_service_account=current_user.is_service_account,
        status=status,
        page=page,
        page_size=page_size,
    )
    return ExperimentListResponse(
        experiments=[_summary_from_model(e) for e in experiments],
        total=total,
        page=page,
        page_size=page_size,
    )


@router.get("/{experiment_id}")
async def get_experiment(
    experiment_id: uuid.UUID,
    db: AsyncSession = Depends(get_db_session),
    current_user: AuthUser = Depends(require_auth),
) -> ExperimentDetail:
    """Get a single experiment by ID."""
    exp = await experiment_service.get_experiment(
        db, experiment_id, user_id=current_user.id, is_service_account=current_user.is_service_account
    )
    if not exp:
        raise HTTPException(status_code=404, detail="Experiment not found")
    return _detail_from_model(exp)


@router.patch("/{experiment_id}")
async def update_experiment(
    experiment_id: uuid.UUID,
    body: ExperimentUpdate,
    db: AsyncSession = Depends(get_db_session),
    current_user: AuthUser = Depends(require_auth),
) -> ExperimentDetail:
    """Update experiment name and/or status."""
    updates = body.model_dump(exclude_none=True)
    if not updates:
        raise HTTPException(status_code=400, detail="No fields to update")
    exp = await experiment_service.update_experiment(
        db, experiment_id, updates, user_id=current_user.id, is_service_account=current_user.is_service_account
    )
    if not exp:
        raise HTTPException(status_code=404, detail="Experiment not found")
    return _detail_from_model(exp)


@router.delete("/{experiment_id}")
async def delete_experiment(
    experiment_id: uuid.UUID,
    db: AsyncSession = Depends(get_db_session),
    current_user: AuthUser = Depends(require_auth),
) -> dict[str, str]:
    """Delete an experiment."""
    deleted = await experiment_service.delete_experiment(
        db, experiment_id, user_id=current_user.id, is_service_account=current_user.is_service_account
    )
    if not deleted:
        raise HTTPException(status_code=404, detail="Experiment not found")
    return {"detail": "Deleted"}


@router.post("/{experiment_id}/results")
async def add_results(
    experiment_id: uuid.UUID,
    body: ResultsEntry,
    db: AsyncSession = Depends(get_db_session),
    current_user: AuthUser = Depends(require_auth),
) -> ResultsResponse:
    """Add or update results for an experiment (incremental entry)."""
    exp = await experiment_service.add_results(
        db, experiment_id, body.results, user_id=current_user.id, is_service_account=current_user.is_service_account
    )
    if not exp:
        raise HTTPException(status_code=404, detail="Experiment not found")
    data = exp.results_data or []
    return ResultsResponse(
        experiment_id=exp.id,
        results_data=data,
        n_results_entered=len(data),
    )


@router.get("/{experiment_id}/results")
async def get_results(
    experiment_id: uuid.UUID,
    db: AsyncSession = Depends(get_db_session),
    current_user: AuthUser = Depends(require_auth),
) -> ResultsResponse:
    """Get current results for an experiment."""
    data, count = await experiment_service.get_results(
        db, experiment_id, user_id=current_user.id, is_service_account=current_user.is_service_account
    )
    if data is None:
        raise HTTPException(status_code=404, detail="Experiment not found")
    return ResultsResponse(
        experiment_id=experiment_id,
        results_data=data,
        n_results_entered=count,
    )
