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
- A virtualenv with dependencies installed (see below). `google-adk` is
  not in the stdlib; `make demo`/`make test` will traceback with
  `ModuleNotFoundError: No module named 'google'` without this step.
- A Gemini API key (`GOOGLE_API_KEY`) only for the live ADK incident agent;
  not required for the probes, validator, job tick, or offline test suite.
- For the cloud deploy path: `gcloud` CLI authenticated, a GCP project
  with billing enabled.

## Set up the environment (once, from the repo root)

```bash
cd /path/to/devpost   # repo root, one level above projects/
python3.11 -m venv .venv
.venv/bin/pip install -r projects/tabclose/requirements.txt
```

Then run every `make` target from `projects/tabclose/` with
`PY=../../.venv/bin/python make <target>`, or export
`PY=$(pwd)/../../.venv/bin/python` once per shell. The Makefile defaults
to plain `python3`, which will not have `google-adk` installed on a fresh
clone; this step is what makes `make demo` actually work rather than
traceback.

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

Runs `demo_local.py`: a scripted transcript of the whole mechanism with
zero network calls, zero GCP credentials, and a fake `classify_fn` in
place of Gemini. It walks the reject case (single-region blip), the accept
case (both observers corroborate), the idempotency claim (a duplicate tick
writes nothing new), and a crash-mid-run resume, asserting each invariant
as it goes (`assert_demo()` exits non-zero if any step lies). This is the
fastest way to see the whole mechanism proven end to end.

```bash
make demo-live
```

Runs `python -m job.main` against the local demo target service
(`demo_target/app.py`, a small FastAPI app you can break on purpose) and
prints the tick result. With the target healthy, Observer A short-circuits
and nothing is written (`return None` in `job/main.py:run_tick_once`,
"most ticks are healthy ticks and shouldn't cost a write"). Break the
target and re-run to see a claim, a validator verdict, and (if both
probes agree) an incident artifact.

**The Gemini call is load-bearing in `demo-live`**, not decorative: once
the validator passes, `job/main.py` calls the ADK incident agent for real.
Set `GOOGLE_API_KEY` before breaking the target, or the run fails with
`ValueError: No API key was provided` at the classification step. Start
the demo target first (`python -m demo_target.app`, listens on `:8080`).

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
