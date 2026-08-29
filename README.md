# Tabclose

Pager duty for a solo founder's one Cloud Run API. Nobody is watching the
laptop. Tabclose watches instead, confirms an outage with a second
independent observer before it believes it, writes the incident file to
GCS, and drafts a status update while the tab is closed.

Track: Taskmaster.

**Status note:** the corroboration validator, both probes, the Cloud Run
Job entrypoint, the ADK incident agent, the artifact writer, the
all-clear path, and the `infra/` deploy scripts are all implemented and
covered by 26 passing local tests, including idempotency and red/green
validator tests. Not yet verified against a real GCP project; see
`progress/PROGRESS.md` for the outstanding preflight blockers (project id,
billing, `gcloud auth`).

## Prerequisites

- Python 3.11+.
- `pip install -r requirements.txt` (or at minimum `google-adk`, `httpx`,
  `fastapi`, plus the shared `agentspine` package on `PYTHONPATH`).
- A Gemini API key (`GOOGLE_API_KEY`) only for the live ADK incident agent;
  not required for the probes, validator, job tick, or offline test suite.
- For the cloud deploy path: `gcloud` CLI authenticated, a GCP project
  with billing enabled.

## Running the mechanism locally

```bash
export PYTHONPATH=.:../shared
```

```bash
make test
```

Runs the full local suite (26 tests): the corroboration validator (the
veto), both probes, the idempotency/crash-resume behavior, the all-clear
path, and a red/green test that breaks the validator on purpose and
confirms it fails, then confirms it passes when restored.

```bash
make demo
```

Runs `python -m job.main` against the local demo target service
(`demo_target/app.py`, a small FastAPI app you can break on purpose) and
prints the tick result. With the target healthy, Observer A short-circuits
and nothing is written (`return None` in `job/main.py:run_tick_once`,
"most ticks are healthy ticks and shouldn't cost a write"). Break the
target and re-run to see a claim, a validator verdict, and (if both
probes agree) an incident artifact.

## Manually firing a tick

```bash
make tick
```

Runs one call to `job.main.main()` locally, outside any Scheduler cadence.

## Running tests locally

```bash
make test
```

Runs the full pytest suite in `tests/` and `validator/tests/`. Verified
26/26 passing locally, including `tests/test_verifier_red_green.py`
(breaks the validator, confirms rejection, restores it, confirms
acceptance) and `tests/test_agent_guard.py` (asserts the ADK agent path is
unreachable unless the validator has already passed).

## Tearing down

```bash
make teardown
```

No-op today since nothing cloud-side is deployed yet; will delete the
Cloud Run Job, Scheduler job, observer function, and empty the GCS bucket
once `infra/` lands.

## Repo layout

```
probes/          observer_a.py (in-process HTTP probe) and observer_b.py
                 (independently implemented probe, deployable standalone
                 to a different region; falls back to in-process when no
                 TABCLOSE_OBSERVER_B_URL is set)
validator/       corroboration.py, the deterministic veto: incident iff
                 both probes fail inside the same detection window
agent/           incident_agent.py, the ADK/Gemini agent that classifies
                 the failure and drafts status.md, reachable only after
                 the validator passes
job/             main.py (Cloud Run Job entrypoint), window.py (window
                 bucketing for the idempotency key), artifact.py (GCS/local
                 writer), allclear.py (recovery detection)
demo_target/     a small FastAPI app you can break on purpose for filming
tests/           26 tests: idempotency, corroboration gate, all-clear,
                 red/green validator verification, agent-unreachable guard
infra/           gcloud deploy/teardown/kill-mid-run scripts, Scheduler wiring
```

See `ARCHITECTURE.md` for the full flow and `LIMITATIONS.md` for what this
does not do.
