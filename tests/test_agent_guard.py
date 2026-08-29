"""tests/test_agent_guard.py — proves the agent cannot run on a rejected
verdict, at the function level (not just "job/main.py happens not to call
it"). This is the "structurally impossible" claim from the prompt: even if
a caller had a rejected Verdict in hand and called draft_incident directly,
it refuses.
"""

from __future__ import annotations

import pytest
from agentspine.validator import Verdict

from agent.incident_agent import draft_all_clear, draft_incident
from tests.conftest import fake_classify_fn, make_probe

T0 = "2026-08-29T06:00:00+00:00"


def test_draft_incident_refuses_rejected_verdict():
    rejected = Verdict(passed=False, evidence={}, reason="single-region blip")
    probe_a = make_probe("us-central1", ok=False, timestamp=T0)
    probe_b = make_probe("europe-west1", ok=True, timestamp=T0)

    with pytest.raises(RuntimeError, match="rejected verdict"):
        draft_incident(rejected, probe_a, probe_b, "some-run-id", "demo-target", classify_fn=fake_classify_fn)


def test_draft_incident_runs_on_passed_verdict():
    passed = Verdict(passed=True, evidence={}, reason="both observers corroborated")
    probe_a = make_probe("us-central1", ok=False, timestamp=T0)
    probe_b = make_probe("europe-west1", ok=False, timestamp=T0)

    draft = draft_incident(passed, probe_a, probe_b, "some-run-id", "demo-target", classify_fn=fake_classify_fn)
    assert draft.classification == "5xx error"
    assert "DRAFT" in draft.status_md
    assert "us-central1" in draft.status_md
    assert "does not overpromise" not in draft.status_md  # instruction text leaked check


def test_draft_all_clear_is_model_free_and_deterministic():
    probe_a = make_probe("us-central1", ok=True, timestamp=T0)
    probe_b = make_probe("europe-west1", ok=True, timestamp=T0)
    md_1 = draft_all_clear("run-123", "demo-target", probe_a, probe_b)
    md_2 = draft_all_clear("run-123", "demo-target", probe_a, probe_b)
    assert md_1 == md_2  # no model call, so it's byte-identical on repeat
    assert "Resolved" in md_1
