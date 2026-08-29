"""Demo target: a tiny service we own so the demo can never flake on someone
else's site.

- GET  /health?region=X  -> 200 {"status": "ok"} unless region X (or "all")
                             is in the broken set, then 503.
- POST /break             -> body {"region": "us-central1"} breaks only that
                             region's path; body {} or {"region": "all"}
                             breaks everything. This is what makes a live,
                             on-camera single-region blip possible: break
                             only us-central1, watch Observer A fail and
                             Observer B (europe-west1) stay healthy, and the
                             corroboration validator reject it.
- POST /fix               -> same shape, clears the given region (or all).
- GET  /status            -> current broken-region set, for narration.

State is a small JSON file, persisted next to the process, so a restart
(Cloud Run scale-to-zero, or re-running locally) doesn't silently un-break
the demo mid-recording. In production this would be a Firestore doc; for a
service this trivial a file next to the process is the smallest thing that
works.
"""

from __future__ import annotations

import json
import os
import time
from pathlib import Path
from typing import Optional

from fastapi import FastAPI, Query, Response
from pydantic import BaseModel

STATE_PATH = Path(os.environ.get("DEMO_TARGET_STATE", "/tmp/tabclose-demo-target-state.json"))

app = FastAPI(title="tabclose-demo-target")


class RegionBody(BaseModel):
    region: Optional[str] = "all"


def _read_state() -> dict:
    if not STATE_PATH.exists():
        return {"broken_regions": []}
    try:
        data = json.loads(STATE_PATH.read_text())
        data.setdefault("broken_regions", [])
        return data
    except (json.JSONDecodeError, OSError):
        return {"broken_regions": []}


def _write_state(broken_regions: list[str]) -> None:
    STATE_PATH.parent.mkdir(parents=True, exist_ok=True)
    STATE_PATH.write_text(json.dumps({"broken_regions": broken_regions}))


def _is_broken_for(region: Optional[str], broken_regions: list[str]) -> bool:
    if "all" in broken_regions:
        return True
    if region and region in broken_regions:
        return True
    return False


@app.get("/health")
def health(response: Response, region: Optional[str] = Query(default=None)):
    state = _read_state()
    if _is_broken_for(region, state["broken_regions"]):
        response.status_code = 503
        return {
            "status": "degraded",
            "detail": f"simulated outage (demo_target /break, region={region!r})",
            "ts": time.time(),
        }
    return {"status": "ok", "ts": time.time()}


@app.post("/break")
def break_it(body: RegionBody = RegionBody()):
    state = _read_state()
    region = body.region or "all"
    if region not in state["broken_regions"]:
        state["broken_regions"].append(region)
    _write_state(state["broken_regions"])
    return {"broken_regions": state["broken_regions"]}


@app.post("/fix")
def fix_it(body: RegionBody = RegionBody()):
    state = _read_state()
    region = body.region or "all"
    if region == "all":
        broken_regions: list[str] = []
    else:
        broken_regions = [r for r in state["broken_regions"] if r != region]
    _write_state(broken_regions)
    return {"broken_regions": broken_regions}


@app.get("/status")
def status():
    return _read_state()


if __name__ == "__main__":
    import uvicorn

    port = int(os.environ.get("PORT", "8080"))
    uvicorn.run(app, host="0.0.0.0", port=port)
