#!/usr/bin/env bash
# infra/demo.sh — runs the exact sequence narrated in the video.
#
# Usage: bash infra/demo.sh PROJECT REGION JOB_NAME BUCKET

set -euo pipefail

PROJECT="${1:?set GCP_PROJECT}"
REGION="${2:-us-central1}"
JOB_NAME="${3:-tabclose-tick}"
BUCKET="${4:-${PROJECT}-tabclose-artifacts}"

DEMO_TARGET_URL="$(gcloud run services describe tabclose-demo-target --project "$PROJECT" --region "$REGION" --format='value(status.url)')"

run_job() {
  echo ">> firing one tick manually (make tick)"
  gcloud run jobs execute "$JOB_NAME" --project "$PROJECT" --region "$REGION" --wait
}

echo "== Step 0: bucket is empty =="
gsutil ls "gs://$BUCKET/incidents/" 2>/dev/null || echo "(empty, as expected)"

echo ""
echo "== Step 1: single-region blip -- break ONLY us-central1 =="
echo "   Observer A (us-central1) will fail. Observer B (europe-west1) stays healthy."
echo "   The corroboration validator must REJECT this: zero artifacts."
curl -s -X POST "$DEMO_TARGET_URL/break" -H 'Content-Type: application/json' -d '{"region":"us-central1"}' | cat
run_job
echo "-- checking the bucket for (lack of) an artifact --"
gsutil ls "gs://$BUCKET/incidents/" 2>/dev/null || echo "(still empty -- rejected run wrote nothing, as expected)"

echo ""
echo "== Step 2: real outage -- break europe-west1 too, both observers now agree =="
curl -s -X POST "$DEMO_TARGET_URL/break" -H 'Content-Type: application/json' -d '{"region":"europe-west1"}' | cat
run_job
echo "-- artifact should now exist --"
gsutil ls -r "gs://$BUCKET/incidents/"

echo ""
echo "== Step 3: crash mid-run, resume, confirm exactly one artifact =="
echo "   run: bash infra/kill_mid_run.sh $PROJECT $REGION $JOB_NAME"
echo "   then re-run this script's Step 2 tick and recount gsutil ls -r above."

echo ""
echo "== Step 4: fix the service, wait for the next tick, confirm all-clear.md =="
curl -s -X POST "$DEMO_TARGET_URL/fix" -H 'Content-Type: application/json' -d '{"region":"all"}' | cat
run_job
gsutil ls -r "gs://$BUCKET/incidents/" | grep all-clear || echo "(all-clear not yet written -- fire one more tick)"
