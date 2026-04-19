"""Unit tests for ``app.services.anthropic_status.AnthropicStatusTracker``.

Pure in-memory — no database, no HTTP. We seed the tracker's internal
deque directly (via its public ``record_*`` methods or, for control over
timestamps, by reaching into ``._samples``) and assert on the derived
``snapshot()`` and ``hourly_rollup()`` shapes.
"""

from __future__ import annotations

import datetime as dt

import pytest

from app.services.anthropic_status import AnthropicStatusTracker


@pytest.fixture
def tracker() -> AnthropicStatusTracker:
    return AnthropicStatusTracker()


def _seed(tracker: AnthropicStatusTracker, samples: list[tuple[dt.datetime, int | None, str, str | None]]) -> None:
    """Bypass the clock to seed samples at specific timestamps."""
    for s in samples:
        tracker._samples.append(s)  # noqa: SLF001 — test-only introspection


def test_empty_tracker_is_ok(tracker: AnthropicStatusTracker) -> None:
    snap = tracker.snapshot()
    assert snap["status"] == "ok"
    assert snap["sample_count"] == 0
    assert snap["p95_latency_ms"] is None
    assert snap["last_error"] is None


def test_five_fast_successes_are_ok(tracker: AnthropicStatusTracker) -> None:
    for _ in range(5):
        tracker.record_success(2000)
    snap = tracker.snapshot()
    assert snap["status"] == "ok"
    assert snap["sample_count"] == 5
    assert snap["error_count"] == 0


def test_five_slow_successes_classify_as_slow(tracker: AnthropicStatusTracker) -> None:
    for _ in range(5):
        tracker.record_success(20_000)
    snap = tracker.snapshot()
    assert snap["status"] == "slow"
    assert snap["p95_latency_ms"] == 20_000


def test_majority_errors_classify_as_down(tracker: AnthropicStatusTracker) -> None:
    tracker.record_error("APIConnectionError")
    tracker.record_success(1500)
    tracker.record_error("APIConnectionError")
    tracker.record_error("APIConnectionError")
    tracker.record_success(1500)
    snap = tracker.snapshot()
    assert snap["status"] == "down"
    assert snap["error_count"] == 3
    assert snap["last_error"] == "APIConnectionError"
    assert snap["last_error_at"] is not None


def test_two_trailing_errors_trip_down_even_on_tiny_window(tracker: AnthropicStatusTracker) -> None:
    # One success long ago, then two errors — the trailing pair rule
    # fires immediately, so users see the banner on a fresh outage.
    tracker.record_success(2000)
    tracker.record_error("APIStatusError")
    tracker.record_error("APIStatusError")
    snap = tracker.snapshot()
    assert snap["status"] == "down"


def test_samples_older_than_five_minutes_are_ignored_by_snapshot(tracker: AnthropicStatusTracker) -> None:
    now = dt.datetime.now(dt.UTC)
    old = now - dt.timedelta(minutes=10)
    # 5 old errors — should be ignored by the banner-facing snapshot.
    _seed(tracker, [(old, None, "error", "APIConnectionError")] * 5)
    # No recent samples.
    snap = tracker.snapshot()
    assert snap["status"] == "ok"
    assert snap["sample_count"] == 0


def test_hourly_rollup_empty_returns_zero_samples(tracker: AnthropicStatusTracker) -> None:
    rollup = tracker.hourly_rollup()
    assert rollup["sample_count"] == 0
    assert rollup["latency_ms_p95"] is None
    assert rollup["error_types"] == {}


def test_hourly_rollup_aggregates_latency_and_error_types(tracker: AnthropicStatusTracker) -> None:
    for ms in [1000, 2000, 3000, 4000, 5000, 10_000]:
        tracker.record_success(ms)
    tracker.record_error("APIConnectionError")
    tracker.record_error("APIConnectionError")
    tracker.record_error("APITimeoutError")

    rollup = tracker.hourly_rollup()
    assert rollup["sample_count"] == 9
    assert rollup["success_count"] == 6
    assert rollup["error_count"] == 3
    assert rollup["error_rate"] == pytest.approx(3 / 9, rel=1e-3)
    assert rollup["latency_ms_max"] == 10_000
    assert rollup["latency_ms_avg"] == (1000 + 2000 + 3000 + 4000 + 5000 + 10_000) // 6
    assert rollup["latency_ms_p50"] in {3000, 4000}  # nearest-rank
    assert rollup["latency_ms_p95"] == 10_000
    assert rollup["error_types"] == {"APIConnectionError": 2, "APITimeoutError": 1}


def test_hourly_rollup_ignores_samples_outside_window(tracker: AnthropicStatusTracker) -> None:
    now = dt.datetime.now(dt.UTC)
    old = now - dt.timedelta(hours=2)
    _seed(tracker, [(old, 1000, "ok", None)] * 3)
    tracker.record_success(2000)
    rollup = tracker.hourly_rollup(window_seconds=3600)
    assert rollup["sample_count"] == 1
    assert rollup["latency_ms_max"] == 2000


def test_reset_clears_state(tracker: AnthropicStatusTracker) -> None:
    tracker.record_success(1000)
    tracker.record_error("APIConnectionError")
    tracker.reset()
    snap = tracker.snapshot()
    assert snap["sample_count"] == 0
    assert snap["last_error"] is None
