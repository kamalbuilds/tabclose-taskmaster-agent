"""job/artifact.py — writes the incident artifact bundle to the configured
ArtifactBackend (LocalBackend for tests/local dev, GcsBackend in prod).

Layout, per DESIGN.md / specs/01-tabclose-taskmaster.md:

    incidents/<run_id>/timeline.json
    incidents/<run_id>/evidence/observer_a.json
    incidents/<run_id>/evidence/observer_b.json
    incidents/<run_id>/status.md
    incidents/<run_id>/all-clear.md   (written later, by job/allclear.py)
"""

from __future__ import annotations

import json
from typing import Any

from agentspine.artifacts import ArtifactBackend


def incident_prefix(run_id: str) -> str:
    return f"incidents/{run_id}"


def write_incident_artifact(
    backend: ArtifactBackend,
    run_id: str,
    timeline: dict[str, Any],
    probe_a: dict,
    probe_b: dict,
    status_md: str,
) -> str:
    """Writes timeline.json, evidence/*.json, and status.md. Returns the
    status.md URI as the primary artifact_uri (what gets stored on the
    Firestore run record).
    """
    prefix = incident_prefix(run_id)

    backend.write(f"{prefix}/timeline.json", json.dumps(timeline, indent=2), content_type="application/json")
    backend.write(
        f"{prefix}/evidence/observer_a.json",
        json.dumps(probe_a, indent=2),
        content_type="application/json",
    )
    backend.write(
        f"{prefix}/evidence/observer_b.json",
        json.dumps(probe_b, indent=2),
        content_type="application/json",
    )
    return backend.write(f"{prefix}/status.md", status_md, content_type="text/markdown")


def write_all_clear(backend: ArtifactBackend, run_id: str, all_clear_md: str) -> str:
    prefix = incident_prefix(run_id)
    return backend.write(f"{prefix}/all-clear.md", all_clear_md, content_type="text/markdown")


def has_all_clear(backend: ArtifactBackend, run_id: str) -> bool:
    return backend.exists(f"{incident_prefix(run_id)}/all-clear.md")
