#!/usr/bin/env bash
# infra/teardown.sh — deletes everything deploy.sh created, in reverse order.
#
# Usage: bash infra/teardown.sh PROJECT REGION_A REGION_B BUCKET JOB_NAME SCHEDULER_NAME

set -euo pipefail

PROJECT="${1:?set GCP_PROJECT}"
REGION_A="${2:-us-central1}"
REGION_B="${3:-europe-west1}"
BUCKET="${4:-${PROJECT}-tabclose-artifacts}"
JOB_NAME="${5:-tabclose-tick}"
SCHEDULER_NAME="${6:-tabclose-scheduler}"

echo "-- deleting Cloud Scheduler job --"
gcloud scheduler jobs delete "$SCHEDULER_NAME" --project "$PROJECT" --location "$REGION_A" --quiet 2>/dev/null \
  || echo "already gone, skipping"

echo "-- deleting Cloud Run Job --"
gcloud run jobs delete "$JOB_NAME" --project "$PROJECT" --region "$REGION_A" --quiet 2>/dev/null \
  || echo "already gone, skipping"

echo "-- deleting demo_target Cloud Run Service --"
gcloud run services delete tabclose-demo-target --project "$PROJECT" --region "$REGION_A" --quiet 2>/dev/null \
  || echo "already gone, skipping"

echo "-- deleting Observer B Cloud Function --"
gcloud functions delete tabclose-observer-b --project "$PROJECT" --region "$REGION_B" --quiet 2>/dev/null \
  || echo "already gone, skipping"

echo "-- emptying and deleting GCS bucket --"
gsutil -m rm -r "gs://$BUCKET" 2>/dev/null || echo "already gone, skipping"

echo "-- removing service accounts --"
gcloud iam service-accounts delete "tabclose-job-sa@${PROJECT}.iam.gserviceaccount.com" --project "$PROJECT" --quiet 2>/dev/null \
  || echo "already gone, skipping"
gcloud iam service-accounts delete "tabclose-scheduler-sa@${PROJECT}.iam.gserviceaccount.com" --project "$PROJECT" --quiet 2>/dev/null \
  || echo "already gone, skipping"

echo ""
echo "== Teardown complete =="
echo "Firestore data ('runs' collection) is left in place; it costs nothing at rest."
echo "Delete the Firestore database manually if you want it fully gone:"
echo "  gcloud firestore databases delete --project $PROJECT --database='(default)' --quiet"
