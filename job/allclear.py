"""job/allclear.py — the later tick that closes an incident.

Stateless by design: rather than a separate Firestore pointer, "which
incidents are still open" is read straight off the artifact store itself.
An incident is open iff `incidents/<run_id>/status.md` exists and
`incidents/<run_id>/all-clear.md` does not. Any tick, on any Cloud Run Job
instance, that lists the bucket sees the same truth -- no extra state to
keep in sync, and it survives a scale-to-zero cold start with zero setup.
"""

from __future__ import annotations

from typing import Callable

from agentspine.artifacts import ArtifactBackend

from agent.incident_agent import draft_all_clear
from job.artifact import has_all_clear, write_all_clear

ProbeFn = Callable[[], dict]


def open_incident_run_ids(backend: ArtifactBackend) -> list[str]:
    """Every run_id under incidents/ that has status.md but no
    all-clear.md yet.
    """
    paths = backend.list_prefix("incidents")
    run_ids = set()
    for path in paths:
        parts = path.split("/")
        # incidents/<run_id>/status.md -> ["incidents", run_id, "status.md"]
        if len(parts) >= 3 and parts[0] == "incidents" and parts[-1] == "status.md":
            run_ids.add(parts[1])
    return sorted(run_id for run_id in run_ids if not has_all_clear(backend, run_id))


def check_and_close_incidents(
    backend: ArtifactBackend,
    service_name: str,
    probe_a_fn: ProbeFn,
    probe_b_fn: ProbeFn,
) -> list[str]:
    """For every open incident, re-probe both observers. If both now report
    healthy, write all-clear.md. Returns the list of run_ids closed on this
    tick (usually 0 or 1 in the demo, but handles multiple open incidents
    honestly rather than assuming there's only ever one).
    """
    closed = []
    open_run_ids = open_incident_run_ids(backend)
    if not open_run_ids:
        return closed

    probe_a = probe_a_fn()
    probe_b = probe_b_fn()
    both_recovered = probe_a.get("ok") is True and probe_b.get("ok") is True
    if not both_recovered:
        return closed

    for run_id in open_run_ids:
        all_clear_md = draft_all_clear(run_id, service_name, probe_a, probe_b)
        write_all_clear(backend, run_id, all_clear_md)
        closed.append(run_id)

    return closed
