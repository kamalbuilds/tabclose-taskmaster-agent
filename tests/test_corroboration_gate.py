"""tests/test_corroboration_gate.py — the core delete-the-validator thesis,
tested end to end through job.main.tick_from_probes (claim -> validate ->
agent+write, exactly the path job/main.py runs on Cloud Run).

specs/01-tabclose-taskmaster.md "Definition of done":
  - single-region blip -> REJECTED, zero artifacts
  - both observers agree -> ACCEPTED, artifact written
"""

from __future__ import annotations

from agentspine.artifacts import LocalBackend
from agentspine.idempotency import MemoryBackend

from job.main import tick_from_probes
from tests.conftest import fake_classify_fn, make_probe

T0 = "2026-08-29T06:00:00+00:00"
T0_PLUS_30S = "2026-08-29T06:00:30+00:00"


def test_single_region_blip_produces_zero_artifacts():
    """Observer A fails, Observer B is fine: this must be REJECTED and must
    write nothing to the artifact backend at all.
    """
    backend = MemoryBackend()
    artifacts = LocalBackend()
    probe_a = make_probe("us-central1", ok=False, timestamp=T0)
    probe_b = make_probe("europe-west1", ok=True, timestamp=T0)

    result = tick_from_probes(
        "demo-target", probe_a, probe_b, backend, artifacts, T0,
        classify_fn=fake_classify_fn,
    )

    assert result.status == "rejected"
    assert result.verdict.passed is False
    assert artifacts.list_prefix("incidents") == []

    record = backend.get(result.run_id)
    assert record.status == "rejected"
    assert record.artifact_uri is None


def test_both_regions_fail_produces_exactly_one_artifact():
    """Observer A and Observer B both fail within the window: this must be
    ACCEPTED and must write exactly one incident folder.
    """
    backend = MemoryBackend()
    artifacts = LocalBackend()
    probe_a = make_probe("us-central1", ok=False, timestamp=T0)
    probe_b = make_probe("europe-west1", ok=False, timestamp=T0_PLUS_30S)

    result = tick_from_probes(
        "demo-target", probe_a, probe_b, backend, artifacts, T0,
        classify_fn=fake_classify_fn,
    )

    assert result.status == "complete"
    assert result.verdict.passed is True

    written = artifacts.list_prefix(f"incidents/{result.run_id}")
    assert f"incidents/{result.run_id}/timeline.json" in written
    assert f"incidents/{result.run_id}/evidence/observer_a.json" in written
    assert f"incidents/{result.run_id}/evidence/observer_b.json" in written
    assert f"incidents/{result.run_id}/status.md" in written

    # exactly one incident folder, not more
    all_run_ids = {p.split("/")[1] for p in artifacts.list_prefix("incidents")}
    assert all_run_ids == {result.run_id}

    status_md = artifacts.read(f"incidents/{result.run_id}/status.md").decode("utf-8")
    assert "DRAFT" in status_md
    assert "us-central1" in status_md or "europe-west1" in status_md


def test_crash_mid_run_then_retry_produces_exactly_one_artifact():
    """Both regions fail. artifact_fn raises on the first attempt
    (simulated crash mid-run, e.g. the job container was killed before the
    GCS write finished). The Scheduler fires again for the same window;
    the retry must complete, and the total artifact count must still be
    exactly one incident folder.
    """
    backend = MemoryBackend()
    artifacts = LocalBackend()
    probe_a = make_probe("us-central1", ok=False, timestamp=T0)
    probe_b = make_probe("europe-west1", ok=False, timestamp=T0_PLUS_30S)

    calls = {"n": 0}

    def crash_once_classify_fn(pa, pb):
        calls["n"] += 1
        if calls["n"] == 1:
            raise RuntimeError("simulated crash mid-run before artifact write")
        return fake_classify_fn(pa, pb)

    import pytest

    with pytest.raises(RuntimeError):
        tick_from_probes(
            "demo-target", probe_a, probe_b, backend, artifacts, T0,
            classify_fn=crash_once_classify_fn,
        )

    # First attempt crashed before completing -- the claim must still be
    # open (not "complete"), so a retry for the same window is allowed.
    from agentspine.idempotency import compute_run_id

    run_id = compute_run_id("demo-target", T0)
    record = backend.get(run_id)
    assert record is not None
    assert record.status == "claimed"
    assert artifacts.list_prefix("incidents") == []

    # Scheduler fires again for the same window.
    result = tick_from_probes(
        "demo-target", probe_a, probe_b, backend, artifacts, T0,
        classify_fn=crash_once_classify_fn,
    )
    assert result.status == "complete"
    assert calls["n"] == 2

    all_run_ids = {p.split("/")[1] for p in artifacts.list_prefix("incidents")}
    assert len(all_run_ids) == 1, f"expected exactly one incident after crash+retry, got {all_run_ids}"

    # A third tick for the same window (e.g. Scheduler fires again after
    # completion) must not write a second artifact.
    result3 = tick_from_probes(
        "demo-target", probe_a, probe_b, backend, artifacts, T0,
        classify_fn=crash_once_classify_fn,
    )
    assert result3.status == "skipped_complete"
    all_run_ids_after = {p.split("/")[1] for p in artifacts.list_prefix("incidents")}
    assert all_run_ids_after == all_run_ids
