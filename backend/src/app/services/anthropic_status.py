"""In-memory rolling health tracker for the Anthropic API dependency.

Passively records outcome (success / error) and latency of every
Anthropic API call made by the agent loop. Two readers consume it:

- ``snapshot()`` — drives the global site banner. Considers the last
  5 minutes of traffic and classifies as ``ok`` / ``slow`` / ``down``.
- ``hourly_rollup()`` — drives the periodic ``admin_events`` log.
  Aggregates a configurable window (default 1 hour) into a JSON-safe
  summary with p50 / p95 / max / avg latency, error counts, and a
  breakdown of error types.

The tracker is a module-level singleton. It uses a ``threading.Lock``
because the agent loop runs inside a worker thread via
``asyncio.to_thread``; reads from asyncio context (the health endpoint,
the hourly snapshot loop) also take the same lock.
"""

from __future__ import annotations

import asyncio
import datetime as dt
import logging
import threading
from collections import deque
from typing import Any

from app.db.session import async_session_factory
from app.services import admin_event_service

logger = logging.getLogger(__name__)

# Banner status window: samples older than this are ignored when
# computing ``snapshot()``. Kept short so the banner reacts quickly.
_BANNER_WINDOW_SECONDS = 300

# Latency threshold above which a 5-sample p95 counts as "slow".
# Typical Sonnet streaming p95 is 3-6 s, so 15 s is well above noise.
_SLOW_P95_MS = 15_000

# Minimum samples required to classify "slow" / "down".
_MIN_SAMPLES_FOR_STATUS = 3
_MIN_SAMPLES_FOR_SLOW = 5

# Rolling buffer size. Large enough for a full busy hour of traffic
# without evicting samples the hourly rollup still needs.
_MAX_SAMPLES = 5000

# How often the background loop writes a snapshot to ``admin_events``.
# "More or less every hour" — sleeps this long from startup, not
# aligned to wall-clock hour boundaries.
_HOURLY_LOOP_SECONDS = 3600


class AnthropicStatusTracker:
    """Thread-safe rolling log of Anthropic call outcomes.

    Each sample is ``(timestamp_utc, latency_ms_or_None, outcome, error_type_or_None)``.
    ``outcome`` is ``"ok"`` or ``"error"``. Latency is ``None`` for error
    samples.
    """

    def __init__(self, max_samples: int = _MAX_SAMPLES) -> None:
        self._samples: deque[tuple[dt.datetime, int | None, str, str | None]] = deque(maxlen=max_samples)
        self._last_error: str | None = None
        self._last_error_at: dt.datetime | None = None
        self._lock = threading.Lock()

    # ------------------------------------------------------------------
    # Writers — called from the agent loop (worker thread).
    # ------------------------------------------------------------------

    def record_success(self, latency_ms: int) -> None:
        now = dt.datetime.now(dt.UTC)
        with self._lock:
            self._samples.append((now, int(latency_ms), "ok", None))

    def record_error(self, error_type: str) -> None:
        now = dt.datetime.now(dt.UTC)
        with self._lock:
            self._samples.append((now, None, "error", error_type))
            self._last_error = error_type
            self._last_error_at = now

    def reset(self) -> None:
        """Test helper — clear all samples and last-error state."""
        with self._lock:
            self._samples.clear()
            self._last_error = None
            self._last_error_at = None

    # ------------------------------------------------------------------
    # Readers.
    # ------------------------------------------------------------------

    def snapshot(self) -> dict[str, Any]:
        """Derive the banner-facing status from the last 5 minutes."""
        now = dt.datetime.now(dt.UTC)
        cutoff = now - dt.timedelta(seconds=_BANNER_WINDOW_SECONDS)

        with self._lock:
            recent = [s for s in self._samples if s[0] >= cutoff]
            last_error = self._last_error
            last_error_at = self._last_error_at

        sample_count = len(recent)
        error_count = sum(1 for s in recent if s[2] == "error")
        error_rate = (error_count / sample_count) if sample_count else 0.0
        latencies = sorted(s[1] for s in recent if s[1] is not None)
        p95 = _percentile(latencies, 95) if latencies else None

        status = _classify(recent, error_rate, sample_count, p95)

        return {
            "status": status,
            "sample_count": sample_count,
            "error_count": error_count,
            "error_rate": round(error_rate, 4),
            "p95_latency_ms": p95,
            "last_error": last_error,
            "last_error_at": last_error_at.isoformat() if last_error_at else None,
            "updated_at": now.isoformat(),
        }

    def hourly_rollup(self, window_seconds: int = _HOURLY_LOOP_SECONDS) -> dict[str, Any]:
        """Aggregate all samples within ``window_seconds`` of now.

        Returns a JSON-serialisable dict suitable for the ``payload``
        column of an ``admin_events`` row. When the window is empty,
        ``sample_count`` is 0 and the caller can choose to skip the
        write.
        """
        now = dt.datetime.now(dt.UTC)
        cutoff = now - dt.timedelta(seconds=window_seconds)

        with self._lock:
            window = [s for s in self._samples if s[0] >= cutoff]

        sample_count = len(window)
        success_count = sum(1 for s in window if s[2] == "ok")
        error_count = sample_count - success_count
        error_rate = (error_count / sample_count) if sample_count else 0.0
        latencies = sorted(s[1] for s in window if s[1] is not None)

        error_types: dict[str, int] = {}
        for s in window:
            if s[3] is not None:
                error_types[s[3]] = error_types.get(s[3], 0) + 1

        return {
            "window_start": cutoff.isoformat(),
            "window_end": now.isoformat(),
            "window_seconds": window_seconds,
            "sample_count": sample_count,
            "success_count": success_count,
            "error_count": error_count,
            "error_rate": round(error_rate, 4),
            "latency_ms_p50": _percentile(latencies, 50) if latencies else None,
            "latency_ms_p95": _percentile(latencies, 95) if latencies else None,
            "latency_ms_max": latencies[-1] if latencies else None,
            "latency_ms_avg": int(sum(latencies) / len(latencies)) if latencies else None,
            "error_types": error_types,
        }


def _percentile(sorted_values: list[int], pct: int) -> int:
    """Nearest-rank percentile on a pre-sorted list of ints."""
    if not sorted_values:
        raise ValueError("empty list")
    k = max(0, min(len(sorted_values) - 1, (pct * len(sorted_values)) // 100))
    return sorted_values[k]


def _classify(
    recent: list[tuple[dt.datetime, int | None, str, str | None]],
    error_rate: float,
    sample_count: int,
    p95: int | None,
) -> str:
    if sample_count >= _MIN_SAMPLES_FOR_STATUS and error_rate >= 0.5:
        return "down"
    # Last two samples both errors → trip down even on a tiny window.
    tail = [s for s in recent[-2:] if s[2] == "error"]
    if len(tail) == 2:
        return "down"
    if sample_count >= _MIN_SAMPLES_FOR_SLOW and p95 is not None and p95 > _SLOW_P95_MS:
        return "slow"
    return "ok"


# Module-level singleton.
status_tracker = AnthropicStatusTracker()


# ---------------------------------------------------------------------------
# Background hourly snapshot loop.
# ---------------------------------------------------------------------------


async def _llm_performance_snapshot_loop(interval_seconds: int = _HOURLY_LOOP_SECONDS) -> None:
    """Persist an ``admin_events`` row approximately every hour.

    The loop is launched from the FastAPI lifespan. It sleeps first so
    a brand-new process does not write an empty-window snapshot on
    startup. Exceptions inside a single iteration are logged but never
    kill the loop.
    """
    while True:
        try:
            await asyncio.sleep(interval_seconds)
        except asyncio.CancelledError:
            raise

        try:
            await _write_hourly_snapshot(interval_seconds)
        except Exception:  # pragma: no cover — defensive; logged and continued.
            logger.exception("llm performance snapshot failed")


async def _write_hourly_snapshot(window_seconds: int) -> None:
    """Compute the rollup and insert an ``admin_events`` row if non-empty."""
    payload = status_tracker.hourly_rollup(window_seconds=window_seconds)
    if payload["sample_count"] == 0:
        return

    message = (
        f"LLM hourly: {payload['sample_count']} calls, "
        f"p95={payload['latency_ms_p95']}ms, "
        f"errors={payload['error_count']}"
    )

    async with async_session_factory() as session:
        try:
            await admin_event_service.log_snapshot(
                session,
                event_type="llm_performance_hourly",
                source="anthropic_status_monitor",
                payload=payload,
                message=message,
            )
            await session.commit()
        except Exception:
            await session.rollback()
            raise
