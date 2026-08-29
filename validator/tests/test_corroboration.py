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
