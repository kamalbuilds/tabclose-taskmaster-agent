"""tests/test_allclear.py — the recovery path: a later tick that sees both
observers healthy writes all-clear.md into the same incident folder, and
only for incidents that are actually still open.
"""

from __future__ import annotations

from agentspine.artifacts import LocalBackend
from agentspine.idempotency import MemoryBackend

from job.allclear import check_and_close_incidents, open_incident_run_ids
from job.main import tick_from_probes
from tests.conftest import fake_classify_fn, make_probe

T0 = "2026-08-29T06:00:00+00:00"
T0_PLUS_30S = "2026-08-29T06:00:30+00:00"


def _make_open_incident(artifacts: LocalBackend) -> str:
    backend = MemoryBackend()
    probe_a = make_probe("us-central1", ok=False, timestamp=T0)
    probe_b = make_probe("europe-west1", ok=False, timestamp=T0_PLUS_30S)
    result = tick_from_probes(
        "demo-target", probe_a, probe_b, backend, artifacts, T0,
        classify_fn=fake_classify_fn,
    )
    assert result.status == "complete"
    return result.run_id


def test_open_incident_run_ids_lists_unresolved_incidents():
    artifacts = LocalBackend()
    run_id = _make_open_incident(artifacts)
    assert open_incident_run_ids(artifacts) == [run_id]


def test_check_and_close_writes_all_clear_when_both_recover():
    artifacts = LocalBackend()
    run_id = _make_open_incident(artifacts)

    healthy_a = make_probe("us-central1", ok=True, timestamp=T0)
    healthy_b = make_probe("europe-west1", ok=True, timestamp=T0)

    closed = check_and_close_incidents(
        artifacts, "demo-target",
        probe_a_fn=lambda: healthy_a,
        probe_b_fn=lambda: healthy_b,
    )

    assert closed == [run_id]
    assert artifacts.exists(f"incidents/{run_id}/all-clear.md")
    assert open_incident_run_ids(artifacts) == []


def test_check_and_close_does_nothing_if_still_failing():
    artifacts = LocalBackend()
    run_id = _make_open_incident(artifacts)

    still_down_a = make_probe("us-central1", ok=False, timestamp=T0)
    still_down_b = make_probe("europe-west1", ok=False, timestamp=T0)

    closed = check_and_close_incidents(
        artifacts, "demo-target",
        probe_a_fn=lambda: still_down_a,
        probe_b_fn=lambda: still_down_b,
    )

    assert closed == []
    assert not artifacts.exists(f"incidents/{run_id}/all-clear.md")


def test_check_and_close_noop_when_no_open_incidents():
    artifacts = LocalBackend()
    healthy_a = make_probe("us-central1", ok=True, timestamp=T0)
    healthy_b = make_probe("europe-west1", ok=True, timestamp=T0)
    closed = check_and_close_incidents(
        artifacts, "demo-target",
        probe_a_fn=lambda: healthy_a,
        probe_b_fn=lambda: healthy_b,
    )
    assert closed == []
