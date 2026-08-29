"""job/main.py — the Cloud Run Job entrypoint. One process, run to
completion, invoked by Cloud Scheduler. This is the "tab closed" part of
the demo: nothing here lives inside an HTTP request/response cycle.

Sequence, matching specs/01-tabclose-taskmaster.md "Flow":
    1. probe A (us-central1, in-process)
    2. if A ok: nothing to corroborate, exit 0 (cheap path, no Firestore
       write at all -- most ticks are healthy ticks and shouldn't cost a
       write)
    3. if A failed: call observer B (europe-west1, over HTTP)
    4. compute run_id = sha256(service, floor(window)) via agentspine
    5. agentspine.run_tick claims the run_id, runs the corroboration
       validator, and — only if it passes — calls the ADK agent to draft
       status.md and writes the incident artifact
    6. separately, check open incidents for recovery and write all-clear.md

`tick_from_probes()` is the network-free core: it takes already-computed
probe dicts and does everything from "compute run_id" onward. This is what
the offline test suite calls directly (see tests/test_idempotency.py,
tests/test_corroboration_gate.py) so the exact same code path that runs on
Cloud Run is exercised with zero network calls and zero GCP credentials.
`run_tick_once()` wraps it with the real probe calls; `main()` wires real
backends from environment variables.
"""

from __future__ import annotations

import logging
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from agentspine.artifacts import ArtifactBackend, GcsBackend, LocalBackend
from agentspine.idempotency import FirestoreBackend, IdempotencyBackend, MemoryBackend
from agentspine.job import TickResult, run_tick

from agent.incident_agent import ClassifyFn, draft_incident
from job.allclear import check_and_close_incidents
from job.artifact import write_incident_artifact
from job.window import current_window
from probes import observer_a, observer_b
from validator.corroboration import CorroborationValidator

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
log = logging.getLogger("tabclose.job")

WINDOW_MINUTES = int(os.environ.get("TABCLOSE_WINDOW_MINUTES", "2"))


def _backends() -> tuple[IdempotencyBackend, ArtifactBackend]:
    """Real GCP backends when configured, local/in-memory otherwise. This is
    what lets `make test` and the offline pytest suite run with zero GCP
    credentials while `job/main.py` on Cloud Run uses the real thing.
    """
    bucket = os.environ.get("TABCLOSE_BUCKET")
    artifact_backend: ArtifactBackend
    if bucket:
        artifact_backend = GcsBackend(bucket)
    else:
        artifact_backend = LocalBackend(os.environ.get("TABCLOSE_LOCAL_ARTIFACT_DIR"))

    use_firestore = os.environ.get("TABCLOSE_USE_FIRESTORE") == "1"
    idempotency_backend: IdempotencyBackend
    if use_firestore:
        idempotency_backend = FirestoreBackend()
    else:
        idempotency_backend = MemoryBackend()

    return idempotency_backend, artifact_backend


def tick_from_probes(
    service_name: str,
    probe_a: dict,
    probe_b: dict,
    idempotency_backend: IdempotencyBackend,
    artifact_backend: ArtifactBackend,
    window_start: str,
    window_seconds: int = WINDOW_MINUTES * 60,
    classify_fn: ClassifyFn | None = None,
) -> TickResult:
    """Network-free core of the tick: takes already-computed probe dicts
    and runs claim -> validate -> (agent + write) via agentspine.run_tick.
    Called by run_tick_once() with live probes, and directly by the offline
    test suite with synthetic probes.
    """
    validator = CorroborationValidator(window_seconds=window_seconds)
    context_extra = {"probe_a": probe_a, "probe_b": probe_b}

    # agentspine.run_tick's context only carries subject/window/run_id by
    # default; the validator needs the probe payloads too, so we wrap it.
    class _ContextInjectingValidator:
        def verdict(self, context):
            merged = {**context, **context_extra}
            return validator.verdict(merged)

    def artifact_fn(context, verdict):
        run_id = context["run_id"]
        draft = draft_incident(
            verdict, probe_a, probe_b, run_id, service_name, classify_fn=classify_fn
        )
        timeline = {
            "run_id": run_id,
            "service": service_name,
            "t0_first_detection": probe_a.get("timestamp"),
            "t1_corroboration": probe_b.get("timestamp"),
            "t2_write": window_start,
            "classification": draft.classification,
            "validator_verdict": {
                "passed": verdict.passed,
                "reason": verdict.reason,
            },
        }
        return write_incident_artifact(
            artifact_backend, run_id, timeline, probe_a, probe_b, draft.status_md
        )

    tick_result = run_tick(
        subject=service_name,
        window=window_start,
        validator=_ContextInjectingValidator(),
        artifact_fn=artifact_fn,
        backend=idempotency_backend,
    )
    log.info("tick result: status=%s run_id=%s", tick_result.status, tick_result.run_id)
    return tick_result


def run_tick_once(
    service_name: str,
    target_url: str,
    idempotency_backend: IdempotencyBackend,
    artifact_backend: ArtifactBackend,
    observer_b_url: str | None = None,
    window_minutes: int = WINDOW_MINUTES,
) -> TickResult | None:
    """One full tick against the real world. Returns None if Observer A
    reported healthy (no claim, no write, no Gemini call for the
    overwhelmingly common "everything is fine" tick) -- otherwise delegates
    to tick_from_probes().
    """
    result_a = observer_a.probe(target_url)
    log.info("observer_a: ok=%s status=%s region=%s", result_a.ok, result_a.status_code, result_a.region)

    if result_a.ok:
        log.info("observer_a healthy, no incident possible this tick, skipping write")
        return None

    if observer_b_url:
        result_b = observer_b.call_observer_b(observer_b_url, target_url)
    else:
        # Local/offline mode: observer_b module runs in-process against the
        # same target. Still a genuinely separate probe() implementation
        # (httpx vs requests, its own dataclass) -- only the network hop to
        # a standalone Cloud Function is skipped when no URL is configured.
        result_b = observer_b.probe(target_url)
    log.info("observer_b: ok=%s status=%s region=%s", result_b.ok, result_b.status_code, result_b.region)

    window_start = current_window(window_minutes)
    return tick_from_probes(
        service_name,
        result_a.to_dict(),
        result_b.to_dict(),
        idempotency_backend,
        artifact_backend,
        window_start,
        window_seconds=window_minutes * 60,
    )


def main() -> int:
    service_name = os.environ.get("TABCLOSE_SERVICE_NAME", "demo-target")
    target_url = os.environ.get("TABCLOSE_TARGET_URL", "http://localhost:8080/health")
    observer_b_url = os.environ.get("TABCLOSE_OBSERVER_B_URL")  # None -> local in-process fallback

    idempotency_backend, artifact_backend = _backends()

    run_tick_once(service_name, target_url, idempotency_backend, artifact_backend, observer_b_url)

    closed = check_and_close_incidents(
        artifact_backend,
        service_name,
        probe_a_fn=lambda: observer_a.probe(target_url).to_dict(),
        probe_b_fn=lambda: (
            observer_b.call_observer_b(observer_b_url, target_url).to_dict()
            if observer_b_url
            else observer_b.probe(target_url).to_dict()
        ),
    )
    if closed:
        log.info("closed incidents: %s", closed)

    return 0


if __name__ == "__main__":
    sys.exit(main())
