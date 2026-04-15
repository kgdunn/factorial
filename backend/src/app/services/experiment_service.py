"""Service layer for experiment CRUD operations.

All functions accept an ``AsyncSession`` so the caller controls the
transaction boundary.  User-scoped operations accept a ``user_id``
parameter to enforce ownership.
"""

from __future__ import annotations

import uuid
from typing import Any

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import SERVICE_USER_ID
from app.models.experiment import Experiment


async def create_experiment(
    db: AsyncSession,
    design_output: dict[str, Any],
    conversation_id: uuid.UUID | None = None,
    user_id: uuid.UUID | None = None,
    name: str | None = None,
) -> Experiment:
    """Create an Experiment from a ``generate_design`` tool output.

    Extracts ``design_type``, factor names, and run count from the tool
    output and stores the full output as ``design_data``.
    """
    design_type = design_output.get("design_type", "unknown")
    n_factors = design_output.get("n_factors", 0)
    n_runs = design_output.get("n_runs", 0)
    factor_names = design_output.get("factor_names", [])

    if not name:
        dt_label = design_type.replace("_", " ").title()
        name = f"{dt_label} ({n_factors} factors, {n_runs} runs)"

    # Build a minimal factor spec from the design output.
    factors_list = [{"name": fn} for fn in factor_names]

    experiment = Experiment(
        name=name,
        status="draft",
        design_type=design_type,
        factors=factors_list,
        design_data=design_output,
        conversation_id=conversation_id,
        user_id=user_id,
    )
    db.add(experiment)
    await db.flush()
    return experiment


def _is_service_user(user_id: uuid.UUID | None) -> bool:
    """Return True if the user_id belongs to a synthetic service/test account."""
    return user_id is None or user_id == SERVICE_USER_ID


async def list_experiments(
    db: AsyncSession,
    user_id: uuid.UUID | None = None,
    status: str | None = None,
    page: int = 1,
    page_size: int = 20,
) -> tuple[list[Experiment], int]:
    """List experiments with optional status filter and pagination.

    Service users (API key) see all experiments; regular users see only their own.
    """
    query = select(Experiment).order_by(Experiment.created_at.desc())
    count_query = select(func.count()).select_from(Experiment)

    if not _is_service_user(user_id):
        query = query.where(Experiment.user_id == user_id)
        count_query = count_query.where(Experiment.user_id == user_id)

    if status:
        query = query.where(Experiment.status == status)
        count_query = count_query.where(Experiment.status == status)

    total_result = await db.execute(count_query)
    total = total_result.scalar() or 0

    offset = (page - 1) * page_size
    query = query.offset(offset).limit(page_size)
    result = await db.execute(query)
    experiments = list(result.scalars().all())

    return experiments, total


async def _get_owned_experiment(
    db: AsyncSession,
    experiment_id: uuid.UUID,
    user_id: uuid.UUID | None,
) -> Experiment | None:
    """Fetch an experiment, checking ownership for non-service users.

    Returns None if not found or if the user doesn't own it.
    """
    experiment = await db.get(Experiment, experiment_id)
    if not experiment:
        return None
    if not _is_service_user(user_id) and experiment.user_id != user_id:
        return None
    return experiment


async def get_experiment(
    db: AsyncSession,
    experiment_id: uuid.UUID,
    user_id: uuid.UUID | None = None,
) -> Experiment | None:
    """Get a single experiment by ID, respecting ownership."""
    return await _get_owned_experiment(db, experiment_id, user_id)


async def update_experiment(
    db: AsyncSession,
    experiment_id: uuid.UUID,
    updates: dict[str, Any],
    user_id: uuid.UUID | None = None,
) -> Experiment | None:
    """Update experiment fields. Returns None if not found or not owned."""
    experiment = await _get_owned_experiment(db, experiment_id, user_id)
    if not experiment:
        return None

    for key, value in updates.items():
        if value is not None:
            setattr(experiment, key, value)

    await db.flush()
    return experiment


async def delete_experiment(
    db: AsyncSession,
    experiment_id: uuid.UUID,
    user_id: uuid.UUID | None = None,
) -> bool:
    """Delete an experiment. Returns True if found, owned, and deleted."""
    experiment = await _get_owned_experiment(db, experiment_id, user_id)
    if not experiment:
        return False
    await db.delete(experiment)
    await db.flush()
    return True


async def add_results(
    db: AsyncSession,
    experiment_id: uuid.UUID,
    results: list[dict[str, Any]],
    user_id: uuid.UUID | None = None,
) -> Experiment | None:
    """Merge new results into the experiment's ``results_data``.

    Uses ``run_index`` as the merge key: existing rows are updated,
    new rows are appended.  Supports incremental entry.
    """
    experiment = await _get_owned_experiment(db, experiment_id, user_id)
    if not experiment:
        return None

    existing = experiment.results_data or []
    existing_by_idx: dict[int, dict[str, Any]] = {r["run_index"]: r for r in existing}

    for row in results:
        idx = row["run_index"]
        existing_by_idx[idx] = {**existing_by_idx.get(idx, {}), **row}

    experiment.results_data = sorted(existing_by_idx.values(), key=lambda r: r["run_index"])
    await db.flush()
    return experiment


async def get_results(
    db: AsyncSession,
    experiment_id: uuid.UUID,
    user_id: uuid.UUID | None = None,
) -> tuple[list[dict[str, Any]] | None, int]:
    """Return ``results_data`` and count of entered results."""
    experiment = await _get_owned_experiment(db, experiment_id, user_id)
    if not experiment:
        return None, 0

    data = experiment.results_data or []
    return data, len(data)
