PY ?= python3
export PYTHONPATH := .:../shared

TARGET_URL ?= http://localhost:8080/health
GCP_REGION ?= us-central1
GCP_REGION_B ?= europe-west1
BUCKET ?= $(GCP_PROJECT)-tabclose-artifacts
JOB_NAME ?= tabclose-tick
SCHEDULER_NAME ?= tabclose-scheduler

.PHONY: deploy demo tick test teardown

test:
	$(PY) -m pytest . -v

demo:
	TABCLOSE_TARGET_URL=$(TARGET_URL) $(PY) -m job.main

tick: demo

deploy:
	bash infra/deploy.sh $(GCP_PROJECT) $(GCP_REGION) $(GCP_REGION_B) $(BUCKET) $(JOB_NAME) $(SCHEDULER_NAME)

teardown:
	bash infra/teardown.sh $(GCP_PROJECT) $(GCP_REGION) $(GCP_REGION_B) $(BUCKET) $(JOB_NAME) $(SCHEDULER_NAME)

kill-mid-run:
	bash infra/kill_mid_run.sh $(GCP_PROJECT) $(GCP_REGION) $(JOB_NAME)
