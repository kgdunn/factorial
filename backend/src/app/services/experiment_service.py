"""Service layer for experiment CRUD operations.

All functions accept an ``AsyncSession`` so the caller controls the
transaction boundary. User-scoped operations accept a ``user_id`` and
enforce ownership unconditionally — there is no bypass.
"""

from __future__ import annotations

import uuid
from typing import Any

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.experiment import Experiment


async def create_experiment(
    db: AsyncSession,
    design_output: dict[str, Any],
    user_id: uuid.UUID,
    conversation_id: uuid.UUID | None = None,
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


async def list_experiments(
    db: AsyncSession,
    user_id: uuid.UUID,
    status: str | None = None,
    page: int = 1,
    page_size: int = 20,
) -> tuple[list[Experiment], int]:
    """List the caller's experiments with optional status filter and pagination."""
    query = select(Experiment).where(Experiment.user_id == user_id).order_by(Experiment.created_at.desc())
    count_query = select(func.count()).select_from(Experiment).where(Experiment.user_id == user_id)

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
    user_id: uuid.UUID,
) -> Experiment | None:
    """Fetch an experiment, returning None if missing or not owned by ``user_id``."""
    experiment = await db.get(Experiment, experiment_id)
    if not experiment:
        return None
    if experiment.user_id != user_id:
        return None
    return experiment


async def get_experiment(
    db: AsyncSession,
    experiment_id: uuid.UUID,
    user_id: uuid.UUID,
) -> Experiment | None:
    """Get a single experiment by ID, respecting ownership."""
    return await _get_owned_experiment(db, experiment_id, user_id)


async def update_experiment(
    db: AsyncSession,
    experiment_id: uuid.UUID,
    updates: dict[str, Any],
    user_id: uuid.UUID,
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
    user_id: uuid.UUID,
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
    user_id: uuid.UUID,
) -> Experiment | None:
    """Merge new results into the experiment's ``results_data``.

    Uses ``run_index`` as the merge key: existing rows are updated,
    new rows are appended.  Supports incremental entry.

    Each row is stored as-is, so optional per-data-point metadata
    keys like ``notes`` (str) and ``included`` (bool, default ``true``
    when absent) round-trip transparently.  Updating a row that
    already carries a ``notes`` value with a payload that omits
    ``notes`` is a no-op for that key — the existing note is
    preserved by the ``{**existing, **row}`` merge below.
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


async def attach_evaluation(
    db: AsyncSession,
    experiment_id: uuid.UUID,
    evaluation: dict[str, Any],
    user_id: uuid.UUID,
) -> Experiment | None:
    """Overwrite ``evaluation_data`` on an experiment.

    Used both by the agent loop (when ``evaluate_design`` runs right after
    ``generate_design``) and by the REST re-evaluate endpoint.
    """
    experiment = await _get_owned_experiment(db, experiment_id, user_id)
    if not experiment:
        return None

    experiment.evaluation_data = evaluation
    await db.flush()
    return experiment


async def get_latest_experiment_for_conversation(
    db: AsyncSession,
    conversation_id: uuid.UUID,
) -> Experiment | None:
    """Return the most recently created experiment in a conversation, or None."""
    result = await db.execute(
        select(Experiment)
        .where(Experiment.conversation_id == conversation_id)
        .order_by(Experiment.created_at.desc())
        .limit(1),
    )
    return result.scalar_one_or_none()


async def get_results(
    db: AsyncSession,
    experiment_id: uuid.UUID,
    user_id: uuid.UUID,
) -> tuple[list[dict[str, Any]] | None, int]:
    """Return ``results_data`` and count of entered results."""
    experiment = await _get_owned_experiment(db, experiment_id, user_id)
    if not experiment:
        return None, 0

    data = experiment.results_data or []
    return data, len(data)
