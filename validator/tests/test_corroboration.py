"""validator/tests/test_corroboration.py — unit tests for the deterministic
veto. Zero network, zero model calls: this is pure arithmetic on
dictionaries, tested as such.
"""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent))

from validator.corroboration import CorroborationValidator, corroborate


def probe(region: str, ok: bool, timestamp: str) -> dict:
    return {
        "region": region,
        "ok": ok,
        "status_code": 200 if ok else 503,
        "body_snippet": "",
        "latency_ms": 1.0,
        "timestamp": timestamp,
        "error": None,
    }


T0 = "2026-08-29T06:00:00+00:00"
T0_PLUS_30S = "2026-08-29T06:00:30+00:00"
T0_PLUS_5MIN = "2026-08-29T06:05:00+00:00"


def test_both_failed_within_window_passes():
    a = probe("us-central1", ok=False, timestamp=T0)
    b = probe("europe-west1", ok=False, timestamp=T0_PLUS_30S)
    verdict = corroborate(a, b, window_seconds=120)
    assert verdict.passed is True
    assert "confirmed" in verdict.reason


def test_single_region_blip_a_only_is_rejected():
    a = probe("us-central1", ok=False, timestamp=T0)
    b = probe("europe-west1", ok=True, timestamp=T0)
    verdict = corroborate(a, b, window_seconds=120)
    assert verdict.passed is False
    assert "did not corroborate" in verdict.reason


def test_single_region_blip_b_only_is_rejected():
    a = probe("us-central1", ok=True, timestamp=T0)
    b = probe("europe-west1", ok=False, timestamp=T0)
    verdict = corroborate(a, b, window_seconds=120)
    assert verdict.passed is False
    assert "observer_a saw no failure" in verdict.reason


def test_both_healthy_is_rejected():
    a = probe("us-central1", ok=True, timestamp=T0)
    b = probe("europe-west1", ok=True, timestamp=T0)
    verdict = corroborate(a, b, window_seconds=120)
    assert verdict.passed is False


def test_both_failed_but_outside_window_is_rejected():
    a = probe("us-central1", ok=False, timestamp=T0)
    b = probe("europe-west1", ok=False, timestamp=T0_PLUS_5MIN)
    verdict = corroborate(a, b, window_seconds=120)
    assert verdict.passed is False
    assert "outside" in verdict.reason


def test_verdict_evidence_contains_both_probes():
    a = probe("us-central1", ok=False, timestamp=T0)
    b = probe("europe-west1", ok=False, timestamp=T0_PLUS_30S)
    verdict = corroborate(a, b, window_seconds=120)
    assert verdict.evidence["probe_a"] == a
    assert verdict.evidence["probe_b"] == b


def test_validator_class_implements_protocol():
    a = probe("us-central1", ok=False, timestamp=T0)
    b = probe("europe-west1", ok=False, timestamp=T0_PLUS_30S)
    v = CorroborationValidator(window_seconds=120)
    verdict = v.verdict({"probe_a": a, "probe_b": b})
    assert verdict.passed is True


def test_unparseable_timestamp_is_rejected_not_crashed():
    a = probe("us-central1", ok=False, timestamp="not-a-timestamp")
    b = probe("europe-west1", ok=False, timestamp=T0)
    verdict = corroborate(a, b, window_seconds=120)
    assert verdict.passed is False
    assert "unparseable" in verdict.reason


# --- Regression: an UNREACHABLE observer must not count as a witness -------
# Found by the final hostile-judge audit. Before this guard,
# `call_observer_b()` returned ok=False when it could not reach Observer B's
# Cloud Function at all (connection refused / cold start / 429 / wrong URL),
# and `corroborate()` read that identical ok=False as "observer B confirms
# the outage". A misconfigured OBSERVER_B_URL in the deploy would therefore
# have turned every single-region blip into a corroborated incident, making
# the entire two-observer gate decoration in production.


def _failing(region, ts="2026-01-01T00:00:00+00:00", observed=True):
    return {
        "region": region,
        "ok": False,
        "status_code": 503,
        "body_snippet": "",
        "latency_ms": 1.0,
        "timestamp": ts,
        "error": None,
        "observed": observed,
    }


def test_unreachable_observer_b_does_not_corroborate():
    """Observer A really saw a 503; Observer B could not be reached at all.
    That is one witness plus one blind spot, not two witnesses."""
    verdict = corroborate(_failing("us-central1"), _failing("europe-west1", observed=False))
    assert verdict.passed is False
    assert "did not actually observe" in verdict.reason


def test_unreachable_observer_a_does_not_corroborate():
    verdict = corroborate(_failing("us-central1", observed=False), _failing("europe-west1"))
    assert verdict.passed is False
    assert "did not actually observe" in verdict.reason


def test_two_real_observations_still_pass():
    """Control: the guard rejects blindness, not genuine corroboration."""
    verdict = corroborate(_failing("us-central1"), _failing("europe-west1"))
    assert verdict.passed is True


def test_call_observer_b_marks_unreachable_as_not_observed():
    """The end-to-end version of the bug: the real client function, pointed
    at a dead port, must self-report observed=False."""
    from probes.observer_b import call_observer_b

    result = call_observer_b("http://127.0.0.1:9/nope", "http://example.com/health")
    assert result.ok is False
    assert result.observed is False, (
        "an unreachable Observer B reported itself as a valid observation"
    )
