#!/usr/bin/env python3
"""demo_local.py — the full Tabclose loop, offline, no GCP, no API key.

Runs the exact code path job/main.py runs on Cloud Run (`tick_from_probes`),
with two things faked and nothing else:
    - the two probes: dicts instead of live HTTP to a deployed target
    - the Gemini call: a deterministic `classify_fn`, the same seam
      job/main.py exposes and tests/conftest.py already uses

Everything downstream of that -- the corroboration validator, agentspine's
idempotency claim, artifact writing, all-clear -- is the real production
code.

Acts:
    1. REJECT: one region sees a 503, the other is healthy. Validator vetoes.
       Zero artifacts. Gemini is never called.
    2. ACCEPT: both regions see the failure inside the window. Validator
       passes, the agent drafts status.md, artifacts appear.
    3. IDEMPOTENCY: Scheduler fires again inside the same window. Same
       run_id, run is already complete, nothing is written twice.
    4. CRASH-RESUME: an artifact write blows up mid-run, the next tick
       retries, and there is still exactly one incident folder.
    5. RECOVERY: both observers come back healthy, all-clear.md is written.

Usage:  ../../.venv/bin/python demo_local.py
"""

from __future__ import annotations

import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from agentspine import transcript as t
from agentspine.artifacts import LocalBackend
from agentspine.idempotency import MemoryBackend, compute_run_id

from job.allclear import check_and_close_incidents
from job.main import tick_from_probes

SERVICE = "demo-target"
WINDOW_START = "2026-08-29T06:00:00+00:00"
T0 = "2026-08-29T06:00:05+00:00"
T0_PLUS_20S = "2026-08-29T06:00:25+00:00"
LATER_WINDOW = "2026-08-29T06:10:00+00:00"


def demo_artifact_root(suffix: str = "") -> str | None:
    """Where artifacts land.

    Default (None) is LocalBackend's own fresh temp dir, which is right for
    tests. For FILMING, demo/record_tabclose.sh sets DEMO_ARTIFACT_DIR to a
    fixed path so demo/watch_artifacts.py can be pointed at that exact
    directory in a second pane and be seen going from empty to non-empty on
    camera. A random temp dir cannot be watched, so the money shot needs this.
    """
    base = os.environ.get("DEMO_ARTIFACT_DIR")
    if not base:
        return None
    root = Path(base) / suffix if suffix else Path(base)
    root.mkdir(parents=True, exist_ok=True)
    return str(root)


def probe(region: str, ok: bool, timestamp: str) -> dict:
    """A ProbeResult-shaped dict, exactly what probes/observer_*.probe()
    returns via .to_dict() -- built here so the demo needs no network."""
    return {
        "region": region,
        "ok": ok,
        "status_code": 200 if ok else 503,
        "body_snippet": "ok" if ok else "upstream connect error or disconnect/reset before headers",
        "latency_ms": 14.2 if ok else 1201.5,
        "timestamp": timestamp,
        "error": None if ok else "HTTPStatusError",
    }


_gemini_calls: list[tuple[str, str]] = []


def fake_classify(probe_a: dict, probe_b: dict) -> str:
    """Deterministic stand-in for the Gemini 3.5 Flash call. Same signature
    and same CLASSIFICATION/STATUS output contract as the real
    `agent.incident_agent._classify_with_gemini`, so the real parser runs
    for real. Records each invocation so the demo can PROVE the model was
    never reached on the rejected path."""
    _gemini_calls.append((probe_a.get("region", "?"), probe_b.get("region", "?")))
    return (
        "CLASSIFICATION: 5xx error\n"
        "STATUS:\n"
        "We are investigating elevated error rates on the API. Requests may "
        "return 503 responses. We have confirmed the issue from two "
        "independent regions and are working on it now. Next update in 10 "
        "minutes."
    )


def incident_dirs(artifacts: LocalBackend) -> list[str]:
    return sorted({p.split("/")[1] for p in artifacts.list_prefix("incidents") if "/" in p})


def main() -> int:
    t.header(
        "TABCLOSE — offline end-to-end demo",
        "Taskmaster track. Zero network, zero GCP, zero API key.\n"
        "Validator: a second probe from an independent region must ALSO see\n"
        "the failure before an incident can be written.",
    )

    idem = MemoryBackend()
    artifacts = LocalBackend(demo_artifact_root())
    t.note(f"idempotency backend: MemoryBackend (FirestoreBackend in prod)")
    t.note(f"artifact backend:    LocalBackend at {artifacts.root_dir} (GcsBackend in prod)")

    # ---------------------------------------------------------------- ACT 1
    t.act(1, "REJECT — a single-region blip is not an incident")
    a_bad = probe("us-central1", ok=False, timestamp=T0)
    b_good = probe("europe-west1", ok=True, timestamp=T0_PLUS_20S)
    t.step("observer A (us-central1) probes the target")
    t.fact("ok", a_bad["ok"])
    t.fact("status_code", a_bad["status_code"])
    t.step("observer B (europe-west1) probes the same target")
    t.fact("ok", b_good["ok"])
    t.fact("status_code", b_good["status_code"])

    before = len(_gemini_calls)
    rejected = tick_from_probes(
        SERVICE, a_bad, b_good, idem, artifacts, WINDOW_START, classify_fn=fake_classify
    )
    # Rendered from the REAL verdict, never a hardcoded False. If the
    # corroboration validator is bypassed (demo/break_validator.sh), this
    # line must visibly flip to PASSED on camera.
    t.verdict_line(
        bool(rejected.verdict and rejected.verdict.passed),
        rejected.verdict.reason if rejected.verdict else "",
    )
    t.fact("run_id", rejected.run_id[:16] + "...")
    t.fact("tick status", rejected.status)
    t.artifacts(
        [f"{artifacts.root_dir}/{p}" for p in sorted(artifacts.list_prefix("incidents"))],
        empty_note="the incident was never written",
    )
    t.fact("Gemini calls this act", len(_gemini_calls) - before)
    t.note("the agent is structurally unreachable on a failed verdict:")
    t.note("run_tick never calls artifact_fn, and draft_incident() raises")
    t.note("if handed a rejected Verdict.")

    t.assert_demo(rejected.status == "rejected", "single-region blip must be rejected")
    t.assert_demo(incident_dirs(artifacts) == [], "rejected run must write zero artifacts")
    t.assert_demo(len(_gemini_calls) == before, "Gemini must not be called on a rejected run")

    # ---------------------------------------------------------------- ACT 2
    t.act(2, "ACCEPT — two independent regions corroborate")
    b_bad = probe("europe-west1", ok=False, timestamp=T0_PLUS_20S)
    t.step("observer A (us-central1) still failing")
    t.fact("ok", a_bad["ok"])
    t.step("observer B (europe-west1) NOW ALSO sees the failure")
    t.fact("ok", b_bad["ok"])
    t.fact("delta between observations", "20s (inside the 120s window)")

    accepted = tick_from_probes(
        SERVICE, a_bad, b_bad, idem, artifacts, WINDOW_START, classify_fn=fake_classify
    )
    t.verdict_line(True, accepted.verdict.reason if accepted.verdict else "")
    t.fact("run_id", accepted.run_id[:16] + "...")
    t.fact("tick status", accepted.status)
    written = sorted(artifacts.list_prefix("incidents"))
    t.artifacts([f"{artifacts.root_dir}/{p}" for p in written])
    t.fact("Gemini calls this act", len(_gemini_calls) - before)

    status_md = artifacts.read(f"incidents/{accepted.run_id}/status.md").decode()
    t.step("status.md (the human-reviewable draft):")
    for ln in status_md.strip().splitlines()[:8]:
        print(f"     | {ln}")
    t.note("DRAFT only. Tabclose does not publish, page, tweet, or restart prod.")

    t.assert_demo(accepted.status == "complete", "corroborated failure must complete")
    t.assert_demo(len(incident_dirs(artifacts)) == 1, "exactly one incident folder")
    t.assert_demo(len(_gemini_calls) == before + 1, "Gemini called exactly once")
    t.assert_demo("DRAFT" in status_md, "status.md must be labelled a draft")

    # ---------------------------------------------------------------- ACT 3
    t.act(3, "IDEMPOTENCY — Scheduler fires again inside the same window")
    t.step("second tick, same (service, window) -> same deterministic run_id")
    t.fact("computed run_id", compute_run_id(SERVICE, WINDOW_START)[:16] + "...")
    t.fact("matches act 2 run_id", compute_run_id(SERVICE, WINDOW_START) == accepted.run_id)

    gemini_before_3 = len(_gemini_calls)
    second = tick_from_probes(
        SERVICE, a_bad, b_bad, idem, artifacts, WINDOW_START, classify_fn=fake_classify
    )
    t.fact("tick status", second.status)
    t.fact("incident folders now", len(incident_dirs(artifacts)))
    t.fact("Gemini calls this act", len(_gemini_calls) - gemini_before_3)
    t.note("this is the 'why a resumable agent might order two laptops' answer:")
    t.note("the claim is checked before any side effect, so tick 2 writes nothing.")

    t.assert_demo(second.status == "skipped_complete", "duplicate tick must skip")
    t.assert_demo(len(incident_dirs(artifacts)) == 1, "still exactly one incident folder")
    t.assert_demo(len(_gemini_calls) == gemini_before_3, "no second Gemini call")

    # ---------------------------------------------------------------- ACT 4
    t.act(4, "CRASH-RESUME — die mid-write, retry, still one artifact")
    crash_idem = MemoryBackend()
    crash_artifacts = LocalBackend(demo_artifact_root('crash-resume'))
    boom = {"n": 0}

    def flaky_classify(pa: dict, pb: dict) -> str:
        boom["n"] += 1
        if boom["n"] == 1:
            raise RuntimeError("simulated Cloud Run instance killed mid-tick")
        return fake_classify(pa, pb)

    t.step("tick 1: the process dies before the artifact is written")
    try:
        tick_from_probes(
            SERVICE, a_bad, b_bad, crash_idem, crash_artifacts, WINDOW_START,
            classify_fn=flaky_classify,
        )
    except RuntimeError as exc:
        t.fact("raised", str(exc))
    crashed_run_id = compute_run_id(SERVICE, WINDOW_START)
    t.fact("run record status", crash_idem.get(crashed_run_id).status)
    t.fact("incident folders", len(incident_dirs(crash_artifacts)))

    t.step("tick 2: Scheduler fires again, the run resumes and finishes")
    resumed = tick_from_probes(
        SERVICE, a_bad, b_bad, crash_idem, crash_artifacts, WINDOW_START,
        classify_fn=flaky_classify,
    )
    t.fact("tick status", resumed.status)
    t.fact("incident folders", len(incident_dirs(crash_artifacts)))
    t.fact("attempts on run record", crash_idem.get(crashed_run_id).attempts)

    t.assert_demo(resumed.status == "complete", "resumed tick must complete")
    t.assert_demo(len(incident_dirs(crash_artifacts)) == 1, "exactly one artifact after crash+resume")

    # ---------------------------------------------------------------- ACT 5
    t.act(5, "RECOVERY — both observers healthy, all-clear is written")
    a_ok = probe("us-central1", ok=True, timestamp=LATER_WINDOW)
    b_ok = probe("europe-west1", ok=True, timestamp=LATER_WINDOW)
    t.step("a later tick re-probes and finds the service back")
    closed = check_and_close_incidents(
        artifacts, SERVICE, probe_a_fn=lambda: a_ok, probe_b_fn=lambda: b_ok
    )
    t.fact("incidents closed", len(closed))
    t.artifacts([f"incidents/{rid}/all-clear.md" for rid in closed])

    t.step("and again (idempotent): nothing left open to close")
    closed_again = check_and_close_incidents(
        artifacts, SERVICE, probe_a_fn=lambda: a_ok, probe_b_fn=lambda: b_ok
    )
    t.fact("incidents closed", len(closed_again))

    t.assert_demo(len(closed) == 1, "the open incident must be closed")
    t.assert_demo(len(closed_again) == 0, "a second close pass must be a no-op")

    # ------------------------------------------------------------- SUMMARY
    t.summary([
        ("single-region blip", "REJECTED, 0 artifacts, 0 Gemini calls"),
        ("two-region corroboration", "ACCEPTED, 1 incident folder written"),
        ("duplicate scheduler tick", "skipped_complete, still 1 folder"),
        ("crash mid-tick then resume", "1 folder, not 2"),
        ("recovery tick", "all-clear.md written once"),
        ("total Gemini calls", str(len(_gemini_calls)) + " (fake, offline)"),
        ("network calls", "0"),
        ("GCP credentials required", "none"),
    ])
    print("\nDelete the corroboration validator and act 1 turns into act 2:")
    print("the blip becomes an incident. That is the whole project.\n")
    return 0


if __name__ == "__main__":
    sys.exit(main())
