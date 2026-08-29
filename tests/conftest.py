"""tests/conftest.py — shared fixtures for the offline test suite. No
network, no GCP credentials: MemoryBackend for idempotency, LocalBackend
(temp dir) for artifacts, and a fake classify_fn so agent/incident_agent.py
never calls the real Gemini API in tests.
"""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import pytest

from agentspine.artifacts import LocalBackend
from agentspine.idempotency import MemoryBackend


@pytest.fixture
def idempotency_backend():
    return MemoryBackend()


@pytest.fixture
def artifact_backend():
    return LocalBackend()


def fake_classify_fn(probe_a: dict, probe_b: dict) -> str:
    """Deterministic stand-in for the Gemini call: no network, no API key
    needed to run the suite. Follows the same CLASSIFICATION/STATUS format
    the real prompt asks for, so agent/incident_agent.py's parser is
    exercised for real.
    """
    return (
        "CLASSIFICATION: 5xx error\n"
        "STATUS:\n"
        f"We are aware {probe_a.get('region')} and {probe_b.get('region')} both "
        "report the service degraded. Investigating now. Next update in 10 minutes."
    )


@pytest.fixture
def classify_fn():
    return fake_classify_fn


def make_probe(region: str, ok: bool, timestamp: str, status_code: int | None = None) -> dict:
    """Build a ProbeResult-shaped dict for tests without importing the real
    probe modules (which hit the network).
    """
    return {
        "region": region,
        "ok": ok,
        "status_code": status_code if status_code is not None else (200 if ok else 503),
        "body_snippet": "ok" if ok else "service unavailable",
        "latency_ms": 12.3,
        "timestamp": timestamp,
        "error": None if ok else "HTTPError",
    }
