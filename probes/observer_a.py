"""Observer A: the primary-region HTTP probe.

Runs inside the Cloud Run Job itself (`us-central1`). Uses the `requests`
library. This is intentionally a different HTTP client than Observer B
(`httpx`), so the two probes do not share a code path beyond "make an HTTP
GET and look at the response" -- see probes/observer_b.py and
ARCHITECTURE.md for why that separation matters to the corroboration
thesis.
"""

from __future__ import annotations

import time
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from typing import Optional

import requests

REGION = "us-central1"


@dataclass
class ProbeResult:
    """Structured evidence a probe returns. Shared shape between A and B so
    the validator can compare them, but the code that produces this shape
    is independent per observer.
    """

    region: str
    ok: bool
    status_code: Optional[int]
    body_snippet: str
    latency_ms: float
    timestamp: str
    error: Optional[str] = None

    def to_dict(self) -> dict:
        return asdict(self)


def probe(url: str, timeout_s: float = 5.0) -> ProbeResult:
    """GET `url` and return structured evidence. Never raises: a connection
    failure, timeout, or non-2xx status is all captured as ok=False with
    whatever detail is available, because the validator needs a result to
    reason about even when the target is completely unreachable.

    Passes `?region=us-central1` so demo_target can simulate a failure
    scoped to just this observer's path (see demo_target/app.py).
    """
    started = time.monotonic()
    timestamp = datetime.now(timezone.utc).isoformat()
    try:
        response = requests.get(url, params={"region": REGION}, timeout=timeout_s)
        latency_ms = (time.monotonic() - started) * 1000
        return ProbeResult(
            region=REGION,
            ok=response.status_code < 400,
            status_code=response.status_code,
            body_snippet=response.text[:500],
            latency_ms=round(latency_ms, 2),
            timestamp=timestamp,
        )
    except requests.RequestException as exc:
        latency_ms = (time.monotonic() - started) * 1000
        return ProbeResult(
            region=REGION,
            ok=False,
            status_code=None,
            body_snippet="",
            latency_ms=round(latency_ms, 2),
            timestamp=timestamp,
            error=str(exc),
        )
