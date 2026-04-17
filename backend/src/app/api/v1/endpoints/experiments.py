"""CRUD endpoints for experiments."""

from __future__ import annotations

import re
import uuid
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi.responses import Response
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import AuthUser, require_auth
from app.db.session import get_db_session
from app.schemas.experiments import (
    EvaluateRequest,
    ExperimentDetail,
    ExperimentListResponse,
    ExperimentSummary,
    ExperimentUpdate,
    ResultsEntry,
    ResultsResponse,
)
from app.schemas.exports import EXPORT_EXTENSIONS, EXPORT_MEDIA_TYPES, ExportFormat
from app.schemas.shares import (
    ShareLinkCreate,
    ShareLinkListResponse,
    ShareLinkResponse,
)
from app.services import experiment_service, export_service, share_service
from app.services.exceptions import ToolExecutionError
from app.services.tools import execute_tool_call

router = APIRouter()


def _slugify(name: str) -> str:
    slug = re.sub(r"[^a-zA-Z0-9]+", "-", name).strip("-").lower()
    return slug or "experiment"


async def _build_export_bytes(
    exp: Any,
    fmt: ExportFormat,
    *,
    include_results: bool,
    share_url: str | None,
) -> bytes:
    if fmt is ExportFormat.csv:
        return export_service.build_csv(exp, include_results=include_results)
    if fmt is ExportFormat.xlsx:
        return export_service.build_xlsx(exp, include_results=include_results)
    if fmt is ExportFormat.md:
        return export_service.build_markdown(exp, include_results=include_results, share_url=share_url)
    if fmt is ExportFormat.pdf:
        return await export_service.build_pdf(exp, include_results=include_results, share_url=share_url)
    raise HTTPException(status_code=400, detail=f"Unsupported format: {fmt}")


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
        evaluation_data=exp.evaluation_data,
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


@router.post("/{experiment_id}/evaluate")
async def evaluate_experiment(
    experiment_id: uuid.UUID,
    body: EvaluateRequest,
    db: AsyncSession = Depends(get_db_session),
    current_user: AuthUser = Depends(require_auth),
) -> ExperimentDetail:
    """Run ``evaluate_design`` on a stored experiment and persist the result.

    Lets users re-run the evaluation with a different assumed sigma or
    alpha without starting a new chat turn.
    """
    exp = await experiment_service.get_experiment(
        db,
        experiment_id,
        user_id=current_user.id,
        is_service_account=current_user.is_service_account,
    )
    if not exp:
        raise HTTPException(status_code=404, detail="Experiment not found")
    design_matrix = (exp.design_data or {}).get("design_coded")
    if not design_matrix:
        raise HTTPException(status_code=400, detail="Experiment has no coded design to evaluate")

    metrics = body.metrics or [
        "d_efficiency",
        "i_efficiency",
        "resolution",
        "alias_structure",
        "vif",
        "condition_number",
        "power",
    ]
    tool_input: dict[str, Any] = {"design_matrix": design_matrix, "metric": metrics}
    if body.assumed_sigma is not None:
        tool_input["sigma"] = body.assumed_sigma
    if body.effect_size is not None:
        tool_input["effect_size"] = body.effect_size
    if body.alpha is not None:
        tool_input["alpha"] = body.alpha

    try:
        evaluation = execute_tool_call("evaluate_design", tool_input)
    except ToolExecutionError as exc:
        raise HTTPException(status_code=400, detail=exc.message) from exc

    if isinstance(evaluation, dict) and "error" in evaluation:
        raise HTTPException(status_code=400, detail=str(evaluation["error"]))

    updated = await experiment_service.attach_evaluation(
        db,
        experiment_id,
        evaluation,
        user_id=current_user.id,
        is_service_account=current_user.is_service_account,
    )
    if not updated:
        raise HTTPException(status_code=404, detail="Experiment not found")
    return _detail_from_model(updated)


# ---------------------------------------------------------------------------
# Exports
# ---------------------------------------------------------------------------


@router.get("/{experiment_id}/export")
async def export_experiment(
    experiment_id: uuid.UUID,
    format: ExportFormat = Query(..., description="Output format: pdf, xlsx, csv, md"),
    acknowledge_share: bool = Query(
        False,
        description=(
            "Required for PDF exports — confirms the owner agrees to embed "
            "analysis plots as static images in the downloaded artifact."
        ),
    ),
    db: AsyncSession = Depends(get_db_session),
    current_user: AuthUser = Depends(require_auth),
) -> Response:
    """Stream a rendered export of the experiment in the requested format."""
    exp = await experiment_service.get_experiment(
        db,
        experiment_id,
        user_id=current_user.id,
        is_service_account=current_user.is_service_account,
    )
    if not exp:
        raise HTTPException(status_code=404, detail="Experiment not found")

    if format is ExportFormat.pdf and not acknowledge_share:
        raise HTTPException(
            status_code=400,
            detail=("PDF exports embed analysis plots as images; call again with acknowledge_share=true to confirm."),
        )

    payload = await _build_export_bytes(exp, format, include_results=True, share_url=None)
    filename = f"{_slugify(exp.name)}.{EXPORT_EXTENSIONS[format]}"
    return Response(
        content=payload,
        media_type=EXPORT_MEDIA_TYPES[format],
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )


# ---------------------------------------------------------------------------
# Share links
# ---------------------------------------------------------------------------


@router.post("/{experiment_id}/shares")
async def create_share_link(
    experiment_id: uuid.UUID,
    body: ShareLinkCreate,
    db: AsyncSession = Depends(get_db_session),
    current_user: AuthUser = Depends(require_auth),
) -> ShareLinkResponse:
    """Mint a new read-only share link for an experiment."""
    share = await share_service.create_share(
        db,
        experiment_id,
        user_id=current_user.id,
        is_service_account=current_user.is_service_account,
        expires_at=body.expires_at,
        never_expire=body.never_expire,
        allow_results=body.allow_results,
    )
    if not share:
        raise HTTPException(status_code=404, detail="Experiment not found")
    return ShareLinkResponse(**share_service.build_share_response_dict(share))


@router.get("/{experiment_id}/shares")
async def list_share_links(
    experiment_id: uuid.UUID,
    db: AsyncSession = Depends(get_db_session),
    current_user: AuthUser = Depends(require_auth),
) -> ShareLinkListResponse:
    """List all share links an owner has minted for an experiment."""
    shares = await share_service.list_shares(
        db,
        experiment_id,
        user_id=current_user.id,
        is_service_account=current_user.is_service_account,
    )
    if shares is None:
        raise HTTPException(status_code=404, detail="Experiment not found")
    return ShareLinkListResponse(
        shares=[ShareLinkResponse(**share_service.build_share_response_dict(s)) for s in shares]
    )


@router.delete("/shares/{token}")
async def revoke_share_link(
    token: str,
    db: AsyncSession = Depends(get_db_session),
    current_user: AuthUser = Depends(require_auth),
) -> dict[str, str]:
    """Revoke a share link.  Idempotent for already-revoked tokens."""
    revoked = await share_service.revoke_share(
        db,
        token,
        user_id=current_user.id,
        is_service_account=current_user.is_service_account,
    )
    if not revoked:
        raise HTTPException(status_code=404, detail="Share not found")
    return {"detail": "Revoked"}


# Expose helpers for the public shares endpoint so it can reuse the same
# filename slug and export pipeline.
__all__ = [
    "router",
    "_slugify",
    "_build_export_bytes",
]
