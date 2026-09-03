#!/usr/bin/env bash
# Tabclose demo — ONE continuous, unedited take. Per JUDGING_CRITERIA_OFFICIAL.md:
# "Live, unedited demo... rules out a screen-recording montage. The video
# must show one continuous take." No post-speed compression, no cuts. Real
# Cloud Run Job cold-start (measured 90-260s per execution during rehearsal)
# means this will likely run longer than the ~4:00 target —
# that is accepted as the honest cost of a real, unedited take over a
# doctored one that hits an arbitrary runtime.
set -uo pipefail
cd /Users/kamal/Desktop/devpost/projects/tabclose
source ~/Desktop/tabclose-cmds.env

mark() {
  echo ""
  echo "########## $1 — $(date -u '+%H:%M:%S UTC') ##########"
}

echo "== Tabclose live demo — $(date -u) =="
echo "Pre-flight clean-state confirmation:"
gsutil ls "gs://$BUCKET/incidents/" 2>&1 || echo "empty, good"
curl -s "$DEMO_TARGET_URL/status"; echo ""

mark "BEAT 1 — problem statement (0:00)"
curl -s "$DEMO_TARGET_URL/health"; echo ""
sleep 2

mark "BEAT 2 — trigger fires, wall clock, nobody typing"
date -u
gcloud run jobs executions list --job="$JOB_NAME" --project "$PROJECT_ID" --region "$GCP_REGION" --limit=5

mark "BEAT 3 — break both regions, fire real incident tick"
curl -s -X POST "$DEMO_TARGET_URL/break" -d '{"region":"us-central1"}' -H 'Content-Type: application/json'; echo ""
curl -s -X POST "$DEMO_TARGET_URL/break" -d '{"region":"europe-west1"}' -H 'Content-Type: application/json'; echo ""
echo "-- bucket before tick --"
gsutil ls "gs://$BUCKET/incidents/" 2>&1 || echo "empty, good"
echo "-- firing tick and waiting for it (real Cloud Run Job execution) --"
gcloud run jobs execute "$JOB_NAME" --project "$PROJECT_ID" --region "$GCP_REGION" --wait

mark "BEAT 4 — artifact appears, read status.md aloud (0:40-1:30)"
gsutil ls "gs://$BUCKET/incidents/"
RUN_ID=$(gsutil ls "gs://$BUCKET/incidents/" | head -1 | sed -E 's#.*/incidents/([^/]+)/#\1#')
echo "run_id=$RUN_ID"
gsutil cat "gs://$BUCKET/incidents/$RUN_ID/timeline.json"; echo ""
gsutil cat "gs://$BUCKET/incidents/$RUN_ID/status.md"

mark "BEAT 5 — single-region blip, fire tick (validator rejects)"
curl -s -X POST "$DEMO_TARGET_URL/fix" -d '{"region":"europe-west1"}' -H 'Content-Type: application/json'; echo ""
curl -s "$DEMO_TARGET_URL/status"; echo ""
FOLDERS_BEFORE=$(gsutil ls "gs://$BUCKET/incidents/" | grep -c '/$')
echo "folders before: $FOLDERS_BEFORE"
gcloud run jobs execute "$JOB_NAME" --project "$PROJECT_ID" --region "$GCP_REGION" --wait
echo "-- bucket after single-region blip (should be unchanged: rejected) --"
gsutil ls "gs://$BUCKET/incidents/" | grep -c '/$'

mark "BEAT 6 — both regions agree, fire tick (writes)"
curl -s -X POST "$DEMO_TARGET_URL/break" -d '{"region":"europe-west1"}' -H 'Content-Type: application/json'; echo ""
curl -s "$DEMO_TARGET_URL/status"; echo ""
gcloud run jobs execute "$JOB_NAME" --project "$PROJECT_ID" --region "$GCP_REGION" --wait
echo "-- new folder exists --"
gsutil ls -r "gs://$BUCKET/incidents/"

mark "BEAT 7 — crash mid-run, resume, exactly one artifact"
bash infra/kill_mid_run.sh "$PROJECT_ID" "$GCP_REGION" "$JOB_NAME"

mark "BEAT 8 — idempotency count + test"
LATEST_RUN=$(gsutil ls "gs://$BUCKET/incidents/" | tail -1 | sed -E 's#.*/incidents/([^/]+)/#\1#')
echo "latest run_id=$LATEST_RUN"
gsutil ls "gs://$BUCKET/incidents/$LATEST_RUN/" | wc -l
../../.venv/bin/python -m pytest tests/test_corroboration_gate.py -v

mark "BEAT 9 — GCP console proof (switch to browser now) + closing ADK line"
echo "Cloud Run Jobs execution history:"
echo "https://console.cloud.google.com/run/jobs/executions?project=$PROJECT_ID"
echo "Cloud Scheduler job detail:"
echo "https://console.cloud.google.com/cloudscheduler?project=$PROJECT_ID"
sleep 3

mark "DONE"
