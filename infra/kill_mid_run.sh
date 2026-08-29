#!/usr/bin/env bash
# infra/kill_mid_run.sh — simulates a crash mid-run for the crash-resume
# demo. Cloud Run Jobs don't give us a clean "SIGKILL this specific task"
# button from the CLI, so we approximate the real thing two ways and pick
# whichever fits the moment being filmed:
#
#   1. (documented, most honest) --task-timeout set low enough that the job
#      is killed by Cloud Run itself mid-execution. We ship the job with a
#      generous 120s timeout for normal operation; for the crash demo,
#      temporarily redeploy with a short timeout so a real execution gets
#      killed, then redeploy with the normal timeout.
#   2. (fast, for local rehearsal) run job/main.py locally and kill -9 the
#      python process after the claim has fired but before the artifact
#      write completes.
#
# This script does (1), which is the one that's honest on camera: it
# doesn't fake anything, it changes a real Cloud Run Job's config to make a
# transient failure actually happen, then puts the config back.
#
# Usage: bash infra/kill_mid_run.sh PROJECT REGION JOB_NAME

set -euo pipefail

PROJECT="${1:?set GCP_PROJECT}"
REGION="${2:-us-central1}"
JOB_NAME="${3:-tabclose-tick}"

echo "-- temporarily setting a 1s task timeout so this execution is killed mid-run --"
gcloud run jobs update "$JOB_NAME" \
  --project "$PROJECT" \
  --region "$REGION" \
  --task-timeout 1s

echo "-- firing the execution (expected to fail/timeout) --"
gcloud run jobs execute "$JOB_NAME" --project "$PROJECT" --region "$REGION" --wait || true

echo "-- restoring the normal 120s task timeout --"
gcloud run jobs update "$JOB_NAME" \
  --project "$PROJECT" \
  --region "$REGION" \
  --task-timeout 120s

echo "-- firing the retry (Scheduler's next tick, or run this now to show it live) --"
gcloud run jobs execute "$JOB_NAME" --project "$PROJECT" --region "$REGION" --wait

echo "Done. Count incident folders with:"
echo "  gsutil ls gs://<bucket>/incidents/ | wc -l"
