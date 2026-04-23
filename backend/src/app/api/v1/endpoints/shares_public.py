"""Unauthenticated read-only endpoints for shared experiment links.

Mounted outside the ``require_auth`` dependency list so anonymous
viewers with a valid token can see a frozen snapshot of an experiment
without creating an account.  ``slowapi`` rate-limits keep the
endpoint from being abused for enumeration or scraping.
"""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Query, Request
from fastapi.responses import Response
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.rate_limit import limiter
from app.api.v1.endpoints.experiments import _build_export_bytes, _slugify
from app.config import settings
from app.db.session import get_db_session
from app.models.user import User
from app.schemas.exports import EXPORT_EXTENSIONS, EXPORT_MEDIA_TYPES, ExportFormat
from app.schemas.shares import PublicExperimentView
from app.services import share_service

router = APIRouter()

# Reproducible-code formats are never exposed on public share links —
# they carry raw tool inputs (and, for ``zip``, the full data file +
# README).  Keeping this set colocated with the share route so reviewers
# see the policy without having to cross-reference the enum.
_PUBLIC_SHARE_REFUSED_FORMATS = frozenset(
    {
        ExportFormat.py,
        ExportFormat.ipynb,
        ExportFormat.md_code,
        ExportFormat.zip,
    }
)


async def _owner_display_name(db: AsyncSession, user_id) -> str | None:
    if user_id is None:
        return None
    user = await db.get(User, user_id)
    return user.display_name if user else None


def _public_view(share, experiment, owner_display_name: str | None) -> PublicExperimentView:
    design_data = experiment.design_data or {}
    return PublicExperimentView(
        id=experiment.id,
        name=experiment.name,
        design_type=experiment.design_type,
        n_runs=design_data.get("n_runs"),
        n_factors=design_data.get("n_factors"),
        factors=experiment.factors,
        design_data=experiment.design_data,
        results_data=experiment.results_data if share.allow_results else None,
        evaluation_data=experiment.evaluation_data,
        owner_display_name=owner_display_name,
        view_count=share.view_count,
        expires_at=share.expires_at,
        created_at=experiment.created_at,
        allow_results=share.allow_results,
        token=share.token,
    )


@router.get("/experiments/{token}")
@limiter.limit(settings.public_share_rate_limit)
async def get_public_experiment(
    request: Request,
    token: str,
    db: AsyncSession = Depends(get_db_session),
) -> PublicExperimentView:
    """Return a read-only snapshot of the experiment behind ``token``."""
    resolved = await share_service.resolve_public_share(db, token)
    if not resolved:
        raise HTTPException(status_code=404, detail="Share not found")
    share, experiment = resolved
    owner_name = await _owner_display_name(db, experiment.user_id)
    return _public_view(share, experiment, owner_name)


@router.get("/experiments/{token}/export")
@limiter.limit(settings.public_share_rate_limit)
async def export_public_experiment(
    request: Request,
    token: str,
    format: ExportFormat = Query(..., description="Output format: pdf, xlsx, csv, md"),
    db: AsyncSession = Depends(get_db_session),
) -> Response:
    """Stream an export of the shared experiment in the requested format.

    Honours ``allow_results``: CSV and XLSX (which are primarily data
    payloads) return 403 when the owner disabled result sharing; PDF
    and Markdown silently omit the response columns.  The reproducible
    code formats (``py`` / ``ipynb`` / ``md_code`` / ``zip``) are never
    exposed on public share links — they carry raw tool inputs and
    belong behind auth.
    """
    resolved = await share_service.resolve_public_share(db, token)
    if not resolved:
        raise HTTPException(status_code=404, detail="Share not found")
    share, experiment = resolved

    if format in _PUBLIC_SHARE_REFUSED_FORMATS:
        raise HTTPException(
            status_code=403,
            detail="Reproducible code export is not available on public share links",
        )

    if not share.allow_results and format in (ExportFormat.csv, ExportFormat.xlsx):
        raise HTTPException(
            status_code=403,
            detail="Results sharing disabled for this link",
        )

    share_url = f"{settings.frontend_url.rstrip('/')}/share/{token}"
    payload = await _build_export_bytes(
        experiment,
        format,
        include_results=share.allow_results,
        share_url=share_url,
    )
    filename = f"{_slugify(experiment.name)}.{EXPORT_EXTENSIONS[format]}"
    return Response(
        content=payload,
        media_type=EXPORT_MEDIA_TYPES[format],
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )
