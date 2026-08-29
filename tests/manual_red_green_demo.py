"""Standalone RED/GREEN demonstration script, run outside pytest, exactly
as the task asked: break the corroboration validator on purpose, confirm a
single-region blip now wrongly creates an incident, restore, confirm it's
rejected again.
"""
import sys
sys.path.insert(0, ".")

from agentspine.artifacts import LocalBackend
from agentspine.idempotency import MemoryBackend
from job.main import tick_from_probes
from tests.conftest import fake_classify_fn, make_probe
import validator.corroboration as corr_module

T0 = "2026-08-29T06:00:00+00:00"

def run_scenario(label):
    backend = MemoryBackend()
    artifacts = LocalBackend()
    probe_a = make_probe("us-central1", ok=False, timestamp=T0)
    probe_b = make_probe("europe-west1", ok=True, timestamp=T0)  # single-region blip: B is FINE

    result = tick_from_probes("demo-target", probe_a, probe_b, backend, artifacts, T0, classify_fn=fake_classify_fn)
    artifact_count = len(artifacts.list_prefix("incidents"))
    print(f"[{label}] tick status={result.status}  artifacts_written={artifact_count}")
    return result, artifact_count

print("=== BEFORE BREAKING: real corroboration.py in place ===")
result, count = run_scenario("baseline (should be GREEN: rejected, 0 artifacts)")
assert result.status == "rejected" and count == 0, "baseline should reject a single-region blip"
print("PASS: single-region blip correctly REJECTED, 0 artifacts.\n")

print("=== BREAKING THE VALIDATOR: patching corroborate() to naive single-observer belief ===")
_original_corroborate = corr_module.corroborate

def naive_broken_corroborate(probe_a, probe_b, window_seconds=120):
    from agentspine.validator import Verdict
    if probe_a.get("ok") is False:
        return Verdict(passed=True, evidence={}, reason="observer_a alone (WRAPPER BUG, no corroboration)")
    return Verdict(passed=False, evidence={}, reason="observer_a ok")

corr_module.corroborate = naive_broken_corroborate

result, count = run_scenario("RED (validator broken)")
print(f"RED OBSERVATION: single-region blip now produced status={result.status}, artifacts={count}")
assert result.status == "complete" and count > 0, "RED case did not reproduce the wrapper bug!"
print("CONFIRMED RED: a single-region blip now WRONGLY created an incident artifact.\n")

print("=== RESTORING the real corroboration.py ===")
corr_module.corroborate = _original_corroborate

result, count = run_scenario("GREEN (validator restored)")
assert result.status == "rejected" and count == 0, "GREEN case failed: validator did not reject after restore!"
print("CONFIRMED GREEN: single-region blip correctly REJECTED again, 0 artifacts.\n")

print("=== RED/GREEN DEMONSTRATION COMPLETE: validator has real veto power. ===")
