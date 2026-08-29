"""tests/test_window.py — window bucketing determinism, unit tested
directly since it's what makes idempotency work across ticks (see
job/window.py docstring).
"""

from __future__ import annotations

from datetime import datetime, timezone

from job.window import floor_to_window


def test_same_window_produces_same_bucket():
    t1 = datetime(2026, 8, 29, 6, 0, 5, tzinfo=timezone.utc)
    t2 = datetime(2026, 8, 29, 6, 1, 55, tzinfo=timezone.utc)  # same 2-min bucket
    assert floor_to_window(t1, 2) == floor_to_window(t2, 2)


def test_different_windows_produce_different_buckets():
    t1 = datetime(2026, 8, 29, 6, 0, 5, tzinfo=timezone.utc)
    t2 = datetime(2026, 8, 29, 6, 2, 5, tzinfo=timezone.utc)  # next 2-min bucket
    assert floor_to_window(t1, 2) != floor_to_window(t2, 2)


def test_bucket_start_is_floored_not_rounded():
    t = datetime(2026, 8, 29, 6, 1, 59, tzinfo=timezone.utc)
    bucket = floor_to_window(t, 2)
    assert bucket.startswith("2026-08-29T06:00:00")
