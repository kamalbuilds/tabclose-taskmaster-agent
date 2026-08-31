#!/usr/bin/env bash
# Tabclose demo — ONE continuous take, no stops, no re-recorded segments.
# Real GCP Cloud Run Job cold-start measured at 90-150s per execution during
# rehearsal. Rather than splice separate takes, this stays a single unbroken
# screen recording; the polling-wait stretches (clearly marked below) get
# time-lapsed (sped up, never cut or faked) in post so the final cut lands
# near 4:00 while every action and result shown is real, in order, and from
# this one take.
set -uo pipefail
cd /Users/kamal/Desktop/devpost/projects/tabclose
source ~/Desktop/tabclose-cmds.env

mark() {
  echo ""
  echo "########## MARK: $1 — $(date -u '+%H:%M:%S UTC') ##########"
}

echo "== Tabclose live demo — $(date -u) =="
echo "Pre-flight clean-state confirmation:"
gsutil ls "gs://$BUCKET/incidents/" 2>&1 || echo "empty, good"
curl -s "$DEMO_TARGET_URL/status"; echo ""

mark "BEAT 1 START — problem statement (0:00)"
curl -s "$DEMO_TARGET_URL/health"; echo ""
sleep 2

mark "BEAT 2 START — trigger fires, wall clock, nobody typing (0:15)"
date -u
gcloud run jobs executions list --job="$JOB_NAME" --project "$PROJECT_ID" --region "$GCP_REGION" --limit=5

mark "BEAT 3 START — break both regions, fire real incident tick"
curl -s -X POST "$DEMO_TARGET_URL/break" -d '{"region":"us-central1"}' -H 'Content-Type: application/json'; echo ""
curl -s -X POST "$DEMO_TARGET_URL/break" -d '{"region":"europe-west1"}' -H 'Content-Type: application/json'; echo ""
echo "-- bucket before tick --"
gsutil ls "gs://$BUCKET/incidents/" 2>&1 || echo "empty, good"
echo "-- firing tick (real Cloud Run Job execution) --"
gcloud run jobs execute "$JOB_NAME" --project "$PROJECT_ID" --region "$GCP_REGION" --async

mark "WAIT-COMPRESS-START — real GCP provisioning, speed up in post"
WAITED=0
while [ "$WAITED" -lt 180 ]; do
  COUNT=$(gsutil ls "gs://$BUCKET/incidents/" 2>/dev/null | grep -c '/$' || true)
  echo "[$(date -u +%H:%M:%S)] incident folders=$COUNT waited=${WAITED}s"
  if [ "$COUNT" -ge 1 ]; then break; fi
  sleep 8
  WAITED=$((WAITED+8))
done
mark "WAIT-COMPRESS-END"

mark "BEAT 4 — artifact appears, read status.md aloud (0:40-1:30)"
gsutil ls "gs://$BUCKET/incidents/"
RUN_ID=$(gsutil ls "gs://$BUCKET/incidents/" | head -1 | sed -E 's#.*/incidents/([^/]+)/#\1#')
echo "run_id=$RUN_ID"
gsutil cat "gs://$BUCKET/incidents/$RUN_ID/timeline.json"; echo ""
gsutil cat "gs://$BUCKET/incidents/$RUN_ID/status.md"

mark "BEAT 5 START — single-region blip, fire tick (validator should reject)"
curl -s -X POST "$DEMO_TARGET_URL/fix" -d '{"region":"europe-west1"}' -H 'Content-Type: application/json'; echo ""
curl -s "$DEMO_TARGET_URL/status"; echo ""
FOLDERS_BEFORE=$(gsutil ls "gs://$BUCKET/incidents/" | grep -c '/$')
echo "folders before: $FOLDERS_BEFORE"
gcloud run jobs execute "$JOB_NAME" --project "$PROJECT_ID" --region "$GCP_REGION" --async

mark "WAIT-COMPRESS-START"
sleep 100
mark "WAIT-COMPRESS-END"

echo "-- bucket after single-region blip (should be unchanged: rejected) --"
gsutil ls "gs://$BUCKET/incidents/" | grep -c '/$'

mark "BEAT 6 START — both regions agree, fire tick (should write)"
curl -s -X POST "$DEMO_TARGET_URL/break" -d '{"region":"europe-west1"}' -H 'Content-Type: application/json'; echo ""
curl -s "$DEMO_TARGET_URL/status"; echo ""
gcloud run jobs execute "$JOB_NAME" --project "$PROJECT_ID" --region "$GCP_REGION" --async

mark "WAIT-COMPRESS-START"
WAITED=0
EXPECT=$((FOLDERS_BEFORE + 1))
while [ "$WAITED" -lt 180 ]; do
  COUNT=$(gsutil ls "gs://$BUCKET/incidents/" 2>/dev/null | grep -c '/$' || true)
  echo "[$(date -u +%H:%M:%S)] folders=$COUNT expect>=$EXPECT waited=${WAITED}s"
  if [ "$COUNT" -ge "$EXPECT" ]; then break; fi
  sleep 8
  WAITED=$((WAITED+8))
done
mark "WAIT-COMPRESS-END"

echo "-- new folder exists --"
gsutil ls -r "gs://$BUCKET/incidents/"

mark "BEAT 7 — crash mid-run, resume, exactly one artifact (real GCP config change)"
bash infra/kill_mid_run.sh "$PROJECT_ID" "$GCP_REGION" "$JOB_NAME"

mark "BEAT 8 — idempotency count + test"
LATEST_RUN=$(gsutil ls "gs://$BUCKET/incidents/" | tail -1 | sed -E 's#.*/incidents/([^/]+)/#\1#')
echo "latest run_id=$LATEST_RUN"
gsutil ls "gs://$BUCKET/incidents/$LATEST_RUN/" | wc -l
../../.venv/bin/python -m pytest tests/test_corroboration_gate.py tests/test_idempotency.py -v

mark "BEAT 9 — GCP console proof (switch to browser now) + closing ADK line"
echo "Cloud Run Jobs execution history:"
echo "https://console.cloud.google.com/run/jobs/executions?project=$PROJECT_ID"
echo "Cloud Scheduler job detail:"
echo "https://console.cloud.google.com/cloudscheduler?project=$PROJECT_ID"
sleep 3

mark "DONE"
