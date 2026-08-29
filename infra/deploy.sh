#!/usr/bin/env bash
# infra/deploy.sh — provisions everything Tabclose needs, in order.
# Every gcloud command is spelled out here; nothing is hidden behind an
# abstraction layer, per README.md "One-command deploy".
#
# Usage: bash infra/deploy.sh PROJECT REGION_A REGION_B BUCKET JOB_NAME SCHEDULER_NAME
# (invoked by `make deploy`, which fills these in from env vars / defaults)

set -euo pipefail

PROJECT="${1:?set GCP_PROJECT}"
REGION_A="${2:-us-central1}"
REGION_B="${3:-europe-west1}"
BUCKET="${4:-${PROJECT}-tabclose-artifacts}"
JOB_NAME="${5:-tabclose-tick}"
SCHEDULER_NAME="${6:-tabclose-scheduler}"

SCHEDULE_CRON="${TABCLOSE_SCHEDULE_CRON:-*/2 * * * *}"  # 2 min for filming; use "*/10 * * * *" in prod
REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../../.." && pwd)"  # devpost/

echo "== Tabclose deploy: project=$PROJECT region_a=$REGION_A region_b=$REGION_B bucket=$BUCKET =="

echo "-- enabling required APIs --"
gcloud services enable \
  run.googleapis.com \
  cloudfunctions.googleapis.com \
  cloudscheduler.googleapis.com \
  firestore.googleapis.com \
  storage.googleapis.com \
  cloudbuild.googleapis.com \
  aiplatform.googleapis.com \
  --project "$PROJECT"

echo "-- GCS artifact bucket --"
gsutil mb -p "$PROJECT" -l "$REGION_A" "gs://$BUCKET" 2>/dev/null || echo "bucket already exists, skipping"

echo "-- Firestore (native mode) --"
gcloud firestore databases create --project "$PROJECT" --location="$REGION_A" 2>/dev/null \
  || echo "Firestore database already exists, skipping"

echo "-- least-privilege service account for the job --"
SA_NAME="tabclose-job-sa"
SA_EMAIL="${SA_NAME}@${PROJECT}.iam.gserviceaccount.com"
gcloud iam service-accounts create "$SA_NAME" \
  --project "$PROJECT" \
  --display-name "Tabclose Cloud Run Job identity" 2>/dev/null \
  || echo "service account already exists, skipping"

# Scoped, not project-wide: storage object admin on the ONE bucket, not
# roles/storage.admin project-wide.
gsutil iam ch "serviceAccount:${SA_EMAIL}:roles/storage.objectAdmin" "gs://$BUCKET"
gcloud projects add-iam-policy-binding "$PROJECT" \
  --member "serviceAccount:${SA_EMAIL}" \
  --role "roles/datastore.user" \
  --condition=None
gcloud projects add-iam-policy-binding "$PROJECT" \
  --member "serviceAccount:${SA_EMAIL}" \
  --role "roles/aiplatform.user" \
  --condition=None

echo "-- Observer B: europe-west1 Cloud Function (separate deploy target) --"
OBS_B_DIR="$(mktemp -d)"
cp "$REPO_ROOT/projects/tabclose/probes/observer_b.py" "$OBS_B_DIR/main.py"
cp "$REPO_ROOT/projects/tabclose/probes/observer_b_requirements.txt" "$OBS_B_DIR/requirements.txt"
gcloud functions deploy tabclose-observer-b \
  --project "$PROJECT" \
  --region "$REGION_B" \
  --runtime python312 \
  --trigger-http \
  --entry-point main \
  --source "$OBS_B_DIR" \
  --allow-unauthenticated \
  --memory 256Mi \
  --timeout 30s
rm -rf "$OBS_B_DIR"
OBSERVER_B_URL="$(gcloud functions describe tabclose-observer-b --project "$PROJECT" --region "$REGION_B" --format='value(serviceConfig.uri)')"
echo "Observer B deployed at: $OBSERVER_B_URL"

echo "-- demo_target: Cloud Run Service (the service we own, deliberately breakable) --"
gcloud builds submit "$REPO_ROOT" \
  --project "$PROJECT" \
  --config /dev/stdin <<EOF
steps:
  - name: gcr.io/cloud-builders/docker
    args: ['build', '-t', 'gcr.io/$PROJECT/tabclose-demo-target', '-f', 'projects/tabclose/demo_target/Dockerfile', '.']
images: ['gcr.io/$PROJECT/tabclose-demo-target']
EOF
gcloud run deploy tabclose-demo-target \
  --project "$PROJECT" \
  --region "$REGION_A" \
  --image "gcr.io/$PROJECT/tabclose-demo-target" \
  --allow-unauthenticated \
  --min-instances 0 --max-instances 2 \
  --memory 256Mi
DEMO_TARGET_URL="$(gcloud run services describe tabclose-demo-target --project "$PROJECT" --region "$REGION_A" --format='value(status.url)')"
echo "demo_target deployed at: $DEMO_TARGET_URL"

echo "-- Tabclose Cloud Run Job image --"
gcloud builds submit "$REPO_ROOT" \
  --project "$PROJECT" \
  --config /dev/stdin <<EOF
steps:
  - name: gcr.io/cloud-builders/docker
    args: ['build', '-t', 'gcr.io/$PROJECT/tabclose-job', '-f', 'projects/tabclose/job/Dockerfile', '.']
images: ['gcr.io/$PROJECT/tabclose-job']
EOF

echo "-- Tabclose Cloud Run Job --"
gcloud run jobs deploy "$JOB_NAME" \
  --project "$PROJECT" \
  --region "$REGION_A" \
  --image "gcr.io/$PROJECT/tabclose-job" \
  --service-account "$SA_EMAIL" \
  --max-retries 1 \
  --task-timeout 120s \
  --set-env-vars "TABCLOSE_BUCKET=$BUCKET,TABCLOSE_USE_FIRESTORE=1,TABCLOSE_SERVICE_NAME=tabclose-demo-target,TABCLOSE_TARGET_URL=${DEMO_TARGET_URL}/health,TABCLOSE_OBSERVER_B_URL=${OBSERVER_B_URL},TABCLOSE_WINDOW_MINUTES=2"

echo "-- Cloud Scheduler trigger --"
SCHEDULER_SA="tabclose-scheduler-sa"
SCHEDULER_SA_EMAIL="${SCHEDULER_SA}@${PROJECT}.iam.gserviceaccount.com"
gcloud iam service-accounts create "$SCHEDULER_SA" \
  --project "$PROJECT" \
  --display-name "Tabclose Scheduler invoker" 2>/dev/null \
  || echo "scheduler service account already exists, skipping"
gcloud run jobs add-iam-policy-binding "$JOB_NAME" \
  --project "$PROJECT" \
  --region "$REGION_A" \
  --member "serviceAccount:${SCHEDULER_SA_EMAIL}" \
  --role "roles/run.invoker"

JOB_EXEC_URI="https://${REGION_A}-run.googleapis.com/apis/run.googleapis.com/v1/namespaces/${PROJECT}/jobs/${JOB_NAME}:run"
gcloud scheduler jobs create http "$SCHEDULER_NAME" \
  --project "$PROJECT" \
  --location "$REGION_A" \
  --schedule "$SCHEDULE_CRON" \
  --uri "$JOB_EXEC_URI" \
  --http-method POST \
  --oauth-service-account-email "$SCHEDULER_SA_EMAIL" \
  2>/dev/null || echo "scheduler job already exists, skipping (update manually if the schedule changed)"

echo ""
echo "== Deploy complete =="
echo "demo_target:   $DEMO_TARGET_URL"
echo "observer_b:    $OBSERVER_B_URL"
echo "job:           $JOB_NAME (region $REGION_A)"
echo "scheduler:     $SCHEDULER_NAME every ${SCHEDULE_CRON} (documented prod cadence: */10 * * * *)"
echo "bucket:        gs://$BUCKET"
