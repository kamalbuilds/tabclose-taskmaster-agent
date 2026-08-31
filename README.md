# Tabclose

Pager duty for a solo founder's one Cloud Run API. Nobody is watching the
laptop. Tabclose watches instead, confirms an outage with a second
independent observer before it believes it, writes the incident file to
GCS, and drafts a status update while the tab is closed.

**Track: The Taskmaster.**

Contest requirements, and where each one lives in this repo:

| Requirement | What this project uses | Where |
|---|---|---|
| Gemini 2.5 Flash or newer | `gemini-2.5-flash` | `agent/incident_agent.py:25` |
| Google agent framework | Agent Development Kit (`google-adk`), `LlmAgent` | `agent/incident_agent.py` |
| Google Cloud service | Cloud Run Jobs, Cloud Scheduler, Firestore, GCS, Cloud Functions (Observer B in a second region) | `infra/deploy.sh` |

## Quick start

Verified from a clean `git clone` into an empty directory, with a fresh
virtualenv and no other setup.

**Python 3.11 or newer is required.** Check first, because the default
`python3` on macOS is often 3.9, and an old `pip` fails the editable
install below with a confusing "requires a setuptools-based build" error
rather than a version error:

```bash
python3 --version        # must be 3.11 or newer; use python3.12 explicitly if not
```

```bash
git clone <this-repo> tabclose
cd tabclose
python3.12 -m venv .venv          # or: python3 -m venv .venv, if python3 is >= 3.11
.venv/bin/pip install --upgrade pip
.venv/bin/pip install -e .
PY=.venv/bin/python make test
PY=.venv/bin/python make demo
```

`pip install -e .` installs every dependency, including the `agentspine`
spine that ships inside this repo. There is no sibling directory to clone
and no `PYTHONPATH` to export.

Expected output: **36 passing tests**, and a demo that exits 0. Both run
fully offline, with no network calls, no GCP credentials, and no API key.
If either needs one, that is a bug in this project.

## Prerequisites

- Python 3.11 or newer.
- For the live Gemini path only (`make demo-live` against a broken target):
  a Gemini API key in `GOOGLE_API_KEY`. Not needed for the probes, the
  validator, the job tick, the offline test suite, or `make demo`.
- For the cloud deploy path: the `gcloud` CLI authenticated, and a GCP
  project with billing enabled.

## What the commands do

```bash
make test
```

The full offline suite (36 tests): the corroboration validator (the veto),
both probes, idempotency and crash-resume, the all-clear path, a red/green
test that breaks the validator on purpose and confirms it fails then
passes once restored, and a guard asserting the ADK agent is unreachable
unless the validator has already passed.

```bash
make demo
```

Runs `demo_local.py`: a scripted transcript of the whole mechanism with
zero network calls, zero GCP credentials, and a fake `classify_fn` in
place of Gemini. It walks the reject case (single-region blip), the accept
case (both observers corroborate), the idempotency claim (a duplicate tick
writes nothing new), and a crash-mid-run resume, asserting each invariant
as it goes. `assert_demo()` exits non-zero if any step lies, so a green
run is a real result rather than a printed story.

```bash
make demo-live
```

Runs `python -m job.main` against the local demo target service
(`demo_target/app.py`, a small FastAPI app you can break on purpose).
With the target healthy, Observer A short-circuits and nothing is written,
because most ticks are healthy ticks and should not cost a write. Break
the target and re-run to see a claim, a validator verdict, and, if both
probes agree, an incident artifact.

The Gemini call is load bearing here, not decorative: once the validator
passes, `job/main.py` calls the ADK incident agent for real. Set
`GOOGLE_API_KEY` before breaking the target, or the run stops at the
classification step. Start the demo target first with
`python -m demo_target.app`, which listens on port 8080.

## Deploying to Google Cloud

```bash
make deploy PROJECT_ID=your-project-id
```

`infra/deploy.sh` enables the required APIs and provisions the GCS
artifact bucket, Firestore, Observer B as a Cloud Function in a second
region, the demo target Cloud Run Service, the Cloud Run Job, and the
Cloud Scheduler trigger. The build context is this repo, so the image
builds from a clean clone with no sibling directory.

```bash
make teardown PROJECT_ID=your-project-id
```

Deletes the Scheduler job, the Cloud Run Job, the observer function, and
the demo target.

**Honest status:** the deploy scripts are written, `shellcheck`-clean, and
their input guards are tested, but they have not been run end to end
against a live billed GCP project. Everything described under "Quick
start" has been verified from a clean clone. See `LIMITATIONS.md`.

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
agentspine/      the shared spine this repo runs on: idempotency claims,
                 artifact backends, the validator interface, the job runner
demo_target/     a small FastAPI app you can break on purpose for filming
tests/           36 tests: idempotency, corroboration gate, all-clear,
                 red/green validator verification, agent-unreachable guard
infra/           gcloud deploy/teardown/kill-mid-run scripts, Scheduler wiring
```

See `ARCHITECTURE.md` for the full flow and `LIMITATIONS.md` for what this
does not do.

## Judging access

This repository will be shared with `testing@devpost.com` and
`cloudhackathons@google.com` so the judges can clone it and run everything
above themselves.
