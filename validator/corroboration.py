"""The corroboration validator: the deterministic veto, the entire thesis of
this project.

Gemini is never allowed to declare an incident on its own belief. This
module computes the verdict with plain arithmetic on two structured probe
results -- no model call anywhere in this file, no exceptions.

Verdict: incident iff BOTH observers report a failure (`ok is False`) AND
both observations fall inside the same detection window (their timestamps
are within `window_seconds` of each other). A single-region blip -- Probe A
fails, Probe B is fine, or vice versa -- must always be rejected.

`agent/incident_agent.py` (the ADK/Gemini agent) is only invoked by
`job/main.py` after `verdict(context).passed` is True. There is no code
path that reaches the model before this function has run and returned
passed=True; see ARCHITECTURE.md "Why the validator has veto power".
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Any

from agentspine.validator import Verdict

DEFAULT_WINDOW_SECONDS = 120.0


def _parse_ts(ts: str) -> datetime:
    # Probe timestamps are ISO 8601 with a trailing "+00:00" or "Z" offset.
    return datetime.fromisoformat(ts.replace("Z", "+00:00"))


@dataclass
class CorroborationValidator:
    """Implements agentspine.validator.Validator. `context["probe_a"]` and
    `context["probe_b"]` must be dicts shaped like ProbeResult.to_dict()
    (region, ok, status_code, body_snippet, latency_ms, timestamp, error).
    """

    window_seconds: float = DEFAULT_WINDOW_SECONDS

    def verdict(self, context: dict[str, Any]) -> Verdict:
        probe_a = context["probe_a"]
        probe_b = context["probe_b"]
        return corroborate(probe_a, probe_b, window_seconds=self.window_seconds)


def corroborate(probe_a: dict, probe_b: dict, window_seconds: float = DEFAULT_WINDOW_SECONDS) -> Verdict:
    """Pure function version, used directly by unit tests and by
    CorroborationValidator.verdict above.
    """
    a_failed = probe_a.get("ok") is False
    b_failed = probe_b.get("ok") is False

    evidence = {"probe_a": probe_a, "probe_b": probe_b, "window_seconds": window_seconds}

    if not a_failed:
        return Verdict(passed=False, evidence=evidence, reason="observer_a saw no failure")
    if not b_failed:
        return Verdict(
            passed=False,
            evidence=evidence,
            reason="observer_a failed but observer_b did not corroborate (single-region blip)",
        )

    try:
        ts_a = _parse_ts(probe_a["timestamp"])
        ts_b = _parse_ts(probe_b["timestamp"])
    except (KeyError, ValueError) as exc:
        return Verdict(passed=False, evidence=evidence, reason=f"unparseable probe timestamp: {exc}")

    delta = abs((ts_a - ts_b).total_seconds())
    within_window = delta <= window_seconds
    evidence["delta_seconds"] = delta

    if not within_window:
        return Verdict(
            passed=False,
            evidence=evidence,
            reason=f"both observers failed but {delta:.1f}s apart, outside {window_seconds}s window",
        )

    return Verdict(
        passed=True,
        evidence=evidence,
        reason="both observers independently confirmed failure within window",
    )
