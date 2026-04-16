"""Service layer for shareable experiment links.

Functions fall into two buckets:
- Owner-scoped: ``create_share``, ``list_shares``, ``revoke_share`` —
  reuse ``experiment_service.get_experiment`` for ownership checks.
- Public: ``resolve_public_share`` — no auth; returns the share and
  its experiment if the token is valid, not revoked, and not expired.
"""

from __future__ import annotations

import secrets
import uuid
from datetime import UTC, datetime, timedelta

from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from app.models.experiment import Experiment
from app.models.experiment_share import ExperimentShare
from app.services import experiment_service


def _frontend_share_url(token: str) -> str:
    base = settings.frontend_url.rstrip("/")
    return f"{base}/share/{token}"


def _default_expiry() -> datetime:
    return datetime.now(UTC) + timedelta(days=settings.share_token_expire_days)


async def create_share(
    db: AsyncSession,
    experiment_id: uuid.UUID,
    user_id: uuid.UUID | None,
    is_service_account: bool,
    *,
    expires_at: datetime | None,
    never_expire: bool,
    allow_results: bool,
) -> ExperimentShare | None:
    """Mint a new share link.  Returns None when the experiment is not owned."""
    experiment = await experiment_service.get_experiment(
        db, experiment_id, user_id=user_id, is_service_account=is_service_account
    )
    if not experiment:
        return None

    if never_expire:
        resolved_expiry: datetime | None = None
    elif expires_at is not None:
        resolved_expiry = expires_at
    else:
        resolved_expiry = _default_expiry()

    token = secrets.token_urlsafe(settings.share_token_length)

    share = ExperimentShare(
        experiment_id=experiment.id,
        token=token,
        created_by=user_id if not is_service_account else None,
        allow_results=allow_results,
        expires_at=resolved_expiry,
    )
    db.add(share)
    await db.flush()
    await db.refresh(share)
    return share


async def list_shares(
    db: AsyncSession,
    experiment_id: uuid.UUID,
    user_id: uuid.UUID | None,
    is_service_account: bool,
) -> list[ExperimentShare] | None:
    """List all shares (active or revoked) for an owned experiment."""
    experiment = await experiment_service.get_experiment(
        db, experiment_id, user_id=user_id, is_service_account=is_service_account
    )
    if not experiment:
        return None

    result = await db.execute(
        select(ExperimentShare)
        .where(ExperimentShare.experiment_id == experiment.id)
        .order_by(ExperimentShare.created_at.desc())
    )
    return list(result.scalars().all())


async def revoke_share(
    db: AsyncSession,
    token: str,
    user_id: uuid.UUID | None,
    is_service_account: bool,
) -> bool:
    """Mark the share with this token as revoked.

    Returns True if the token existed, belonged to an owned experiment,
    and was revoked (or was already revoked).
    """
    result = await db.execute(select(ExperimentShare).where(ExperimentShare.token == token))
    share = result.scalar_one_or_none()
    if not share:
        return False

    experiment = await experiment_service.get_experiment(
        db, share.experiment_id, user_id=user_id, is_service_account=is_service_account
    )
    if not experiment:
        return False

    if share.revoked_at is None:
        share.revoked_at = datetime.now(UTC)
        await db.flush()
    return True


async def resolve_public_share(
    db: AsyncSession,
    token: str,
) -> tuple[ExperimentShare, Experiment] | None:
    """Look up a share by token and return it alongside the experiment.

    Returns None when the token is unknown, revoked, or expired.  On
    success, atomically increments ``view_count``.
    """
    result = await db.execute(select(ExperimentShare).where(ExperimentShare.token == token))
    share = result.scalar_one_or_none()
    if not share:
        return None

    if share.revoked_at is not None:
        return None

    if share.expires_at is not None:
        # Compare in UTC even if the column came back naive on SQLite.
        expiry = share.expires_at
        if expiry.tzinfo is None:
            expiry = expiry.replace(tzinfo=UTC)
        if expiry <= datetime.now(UTC):
            return None

    experiment = await db.get(Experiment, share.experiment_id)
    if not experiment:
        return None

    await db.execute(
        update(ExperimentShare).where(ExperimentShare.id == share.id).values(view_count=ExperimentShare.view_count + 1)
    )
    await db.flush()
    await db.refresh(share)
    return share, experiment


def build_share_response_dict(share: ExperimentShare) -> dict:
    """Shape an ``ExperimentShare`` for the ``ShareLinkResponse`` schema."""
    return {
        "id": share.id,
        "token": share.token,
        "url": _frontend_share_url(share.token),
        "allow_results": share.allow_results,
        "expires_at": share.expires_at,
        "revoked_at": share.revoked_at,
        "view_count": share.view_count,
        "created_at": share.created_at,
    }
