"""Observer B: the independent second-region probe.

Deployed separately as a Cloud Function in `europe-west1` (see
infra/deploy.sh). Deliberately uses a different HTTP client (`httpx`
instead of `requests`) and lives in a different deploy artifact than
Observer A, so "independent" is true at the infrastructure level too, not
just a flag in a config file: if Probe A's code, its Cloud Run Job, or its
`us-central1` egress path breaks, Probe B is unaffected because it runs as
its own Cloud Function with its own runtime and its own network path.

`probe()` is the pure function both the Cloud Function entrypoint (`main`,
Functions Framework contract) and the offline test suite call. The job
itself talks to Observer B over HTTP (via `call_observer_b`) exactly the
way Cloud Scheduler or another service would, so the "separate function"
claim is exercised for real rather than just imported as a Python module.
"""

from __future__ import annotations

import time
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from typing import Optional

import httpx

REGION = "europe-west1"


@dataclass
class ProbeResult:
    region: str
    ok: bool
    status_code: Optional[int]
    body_snippet: str
    latency_ms: float
    timestamp: str
    error: Optional[str] = None
    # True only when this probe actually reached the target and formed an
    # opinion about it. False means "we could not observe" -- which is NOT
    # the same as "we observed a failure". Collapsing those two into ok=False
    # would let an unreachable Observer B silently corroborate every
    # single-region blip, defeating the entire corroboration thesis.
    observed: bool = True

    def to_dict(self) -> dict:
        return asdict(self)


def probe(url: str, timeout_s: float = 5.0) -> ProbeResult:
    """GET `url` with httpx and return structured evidence. Never raises,
    same contract as observer_a.probe -- see that module's docstring.

    Passes `?region=europe-west1` so demo_target can simulate a failure
    scoped to just this observer's path.
    """
    started = time.monotonic()
    timestamp = datetime.now(timezone.utc).isoformat()
    try:
        response = httpx.get(url, params={"region": REGION}, timeout=timeout_s)
        latency_ms = (time.monotonic() - started) * 1000
        return ProbeResult(
            region=REGION,
            ok=response.status_code < 400,
            status_code=response.status_code,
            body_snippet=response.text[:500],
            latency_ms=round(latency_ms, 2),
            timestamp=timestamp,
        )
    except httpx.HTTPError as exc:
        # This probe DID reach the network and the target refused/timed out:
        # that is a real observation of a failing target, so observed=True.
        latency_ms = (time.monotonic() - started) * 1000
        return ProbeResult(
            region=REGION,
            ok=False,
            status_code=None,
            body_snippet="",
            latency_ms=round(latency_ms, 2),
            timestamp=timestamp,
            error=str(exc),
            observed=True,
        )


def call_observer_b(function_url: str, target_url: str, timeout_s: float = 8.0) -> ProbeResult:
    """What the Cloud Run Job actually calls: an HTTP request to the deployed
    Observer B Cloud Function, passing along the target to probe. This keeps
    Observer A's job process from ever importing and running Observer B's
    probe() in-process -- the two only communicate over the network, which is
    the real independence the corroboration thesis depends on.
    """
    started = time.monotonic()
    timestamp = datetime.now(timezone.utc).isoformat()
    try:
        response = httpx.post(function_url, json={"target_url": target_url}, timeout=timeout_s)
        response.raise_for_status()
        data = response.json()
        data.setdefault("observed", True)
        return ProbeResult(**data)
    except (httpx.HTTPError, ValueError, TypeError) as exc:
        # We could not reach OBSERVER B ITSELF, so we learned nothing about
        # the target. observed=False makes the validator reject rather than
        # treat our own blindness as a second confirming witness.
        latency_ms = (time.monotonic() - started) * 1000
        return ProbeResult(
            region=REGION,
            ok=False,
            status_code=None,
            body_snippet="",
            latency_ms=round(latency_ms, 2),
            timestamp=timestamp,
            error=f"observer_b unreachable: {exc}",
            observed=False,
        )


def main(request):
    """Cloud Functions (Functions Framework) HTTP entrypoint for the
    europe-west1 deploy target. Expects JSON body {"target_url": "..."} and
    returns the ProbeResult as JSON. This is the function `infra/deploy.sh`
    deploys with `gcloud functions deploy`.
    """
    body = request.get_json(silent=True) or {}
    target_url = body.get("target_url")
    if not target_url:
        return ({"error": "target_url required"}, 400)
    result = probe(target_url)
    return (result.to_dict(), 200)
