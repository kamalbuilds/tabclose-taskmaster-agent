"""tests/test_verifier_red_green.py — the delete-the-validator test itself,
automated.

AIM.md / DESIGN.md: "if deleting the validator leaves the demo working, the
project is a wrapper." This test proves the opposite is true here by
literally monkeypatching corroborate() to the naive "believe observer A
alone" logic that a wrapper would use, confirming the demo *breaks*
(RED: a single-region blip now wrongly creates an incident), then restoring
the real function and confirming GREEN.

This is also run manually as part of the required red/green demonstration
(see README "Verification" / the task report), but codifying it as a test
means CI catches a regression to the wrapper behavior automatically.
"""

from __future__ import annotations

import validator.corroboration as corroboration_module
from agentspine.artifacts import LocalBackend
from agentspine.idempotency import MemoryBackend

from job.main import tick_from_probes
from tests.conftest import fake_classify_fn, make_probe

T0 = "2026-08-29T06:00:00+00:00"


def _naive_single_observer_corroborate(probe_a, probe_b, window_seconds=120):
    """What a wrapper would ship: believe observer A's belief alone. This is
    the broken behavior we prove the real corroborate() prevents.
    """
    from agentspine.validator import Verdict

    if probe_a.get("ok") is False:
        return Verdict(passed=True, evidence={"probe_a": probe_a}, reason="observer_a alone (WRAPPER BUG)")
    return Verdict(passed=False, evidence={"probe_a": probe_a}, reason="observer_a ok")


def test_red_single_region_blip_wrongly_creates_incident_when_validator_is_broken(monkeypatch):
    """RED: with the real corroborate() replaced by the naive single-observer
    version, a single-region blip (A fails, B fine) must now WRONGLY produce
    an accepted incident with an artifact written. This demonstrates the
    validator has real veto power -- remove it and the demo breaks exactly
    as AIM.md predicts.
    """
    monkeypatch.setattr(corroboration_module, "corroborate", _naive_single_observer_corroborate)
    # CorroborationValidator.verdict calls the module-level corroborate();
    # re-import inside job.main picks up the patched module attribute since
    # Python resolves it at call time, not import time -- but job.main
    # imports the class, not the function, and the class method calls
    # corroboration_module-local `corroborate` by name at call time within
    # the same module, so patching the module attribute here does affect it.

    backend = MemoryBackend()
    artifacts = LocalBackend()
    probe_a = make_probe("us-central1", ok=False, timestamp=T0)
    probe_b = make_probe("europe-west1", ok=True, timestamp=T0)  # B is FINE, single-region blip

    result = tick_from_probes(
        "demo-target", probe_a, probe_b, backend, artifacts, T0,
        classify_fn=fake_classify_fn,
    )

    # THIS IS THE BUG BEING DEMONSTRATED: with the validator broken, a
    # single-region blip is now (wrongly) accepted and an artifact IS written.
    assert result.status == "complete", "RED case failed to reproduce: broken validator should have accepted"
    written = artifacts.list_prefix(f"incidents/{result.run_id}")
    assert any(p.endswith("status.md") for p in written), "RED case: expected a wrongly-written artifact"


def test_green_same_scenario_is_rejected_once_validator_is_restored():
    """GREEN: same single-region-blip scenario, real corroborate() in
    place (no monkeypatch active in this test), must be REJECTED with zero
    artifacts written. This is the restored/correct behavior.
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
    assert artifacts.list_prefix("incidents") == []
