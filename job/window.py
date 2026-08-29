"""job/window.py — deterministic detection-window bucketing.

`run_id` must be derived from (service, window_start), not from "now", so
that two ticks landing inside the same outage window collapse onto the same
idempotency claim (see agentspine.idempotency.compute_run_id and
DESIGN.md's idempotency section). This module owns the one arithmetic
operation that turns "the current wall-clock time" into a stable window
boundary.
"""

from __future__ import annotations

import math
from datetime import datetime, timezone


def floor_to_window(dt: datetime, window_minutes: int) -> str:
    """Floor `dt` to the start of its `window_minutes`-wide bucket, in UTC,
    and return it as an ISO 8601 string (the canonical window_start used
    everywhere else). Two timestamps inside the same bucket floor to the
    same string, which is what makes them collapse onto one run_id.
    """
    dt = dt.astimezone(timezone.utc)
    epoch_minutes = dt.timestamp() / 60.0
    window_index = math.floor(epoch_minutes / window_minutes)
    bucket_start_minutes = window_index * window_minutes
    bucket_start = datetime.fromtimestamp(bucket_start_minutes * 60.0, tz=timezone.utc)
    return bucket_start.isoformat()


def current_window(window_minutes: int) -> str:
    return floor_to_window(datetime.now(timezone.utc), window_minutes)
