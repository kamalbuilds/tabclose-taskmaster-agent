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


def test_classify_fn_default_is_the_real_gemini_call():
    """The dangerous failure mode this guards: if `classify_fn` defaulted
    to a deterministic stand-in, every production tick would silently
    fabricate an incident classification while looking like it called the
    model. The default must be the real call, with fakes injected by name
    at the call site (as tests/conftest.py and demo_local.py both do).
    """
    import inspect

    from agent import incident_agent

    sig = inspect.signature(incident_agent.draft_incident)
    # The default is None, resolved inside the function to the real call.
    assert sig.parameters["classify_fn"].default is None

    source = inspect.getsource(incident_agent.draft_incident)
    assert "classify_fn or _classify_with_gemini" in source

    # And the real call really does go through ADK + google.genai, rather
    # than being a differently-named stand-in.
    real_source = inspect.getsource(incident_agent._classify_with_gemini)
    assert "LlmAgent" in real_source
    assert "InMemoryRunner" in real_source
    assert incident_agent.MODEL_NAME.startswith("gemini-3")


def test_draft_incident_with_no_classify_fn_attempts_a_real_call(monkeypatch):
    """Proves the default is wired, not just named: with no key set, an
    un-injected call must fail loudly from the model layer rather than
    return a fabricated draft."""
    import pytest

    monkeypatch.delenv("GOOGLE_API_KEY", raising=False)
    monkeypatch.delenv("GEMINI_API_KEY", raising=False)

    passed = Verdict(passed=True, evidence={}, reason="both observers corroborated")
    probe_a = make_probe("us-central1", ok=False, timestamp=T0)
    probe_b = make_probe("europe-west1", ok=False, timestamp=T0)

    with pytest.raises(Exception) as excinfo:
        draft_incident(passed, probe_a, probe_b, "run-x", "demo-target")
    # google-genai raises ValueError("No API key was provided...").
    assert "api key" in str(excinfo.value).lower()
