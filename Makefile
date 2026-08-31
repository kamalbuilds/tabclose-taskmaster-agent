# Tabclose — everything runs from THIS directory. This repo is standalone:
# `pip install -e .` puts agentspine and every dependency in your venv, so no
# PYTHONPATH juggling and no sibling directories are required.
#
#   PY=/path/to/venv/bin/python make test
# or just `make test` after activating the venv.
PY ?= $(if $(wildcard ../../.venv/bin/python),../../.venv/bin/python,python3)

TARGET_URL ?= http://localhost:8080/health
GCP_REGION ?= us-central1
GCP_REGION_B ?= europe-west1

.PHONY: install deploy demo demo-live tick test teardown kill-mid-run

install:
	$(PY) -m pip install -e .

test:
	$(PY) -m pytest . -v

demo:
	$(PY) demo_local.py

demo-live:
	TABCLOSE_TARGET_URL=$(TARGET_URL) $(PY) -m job.main

tick: demo-live

BUCKET ?= $(PROJECT_ID)-tabclose-artifacts
JOB_NAME ?= tabclose-tick
SCHEDULER_NAME ?= tabclose-scheduler

deploy:
	@test -n "$(PROJECT_ID)" || { echo "usage: make deploy PROJECT_ID=<gcp-project>"; exit 1; }
	bash infra/deploy.sh $(PROJECT_ID) $(GCP_REGION) $(GCP_REGION_B) $(BUCKET) $(JOB_NAME) $(SCHEDULER_NAME)

teardown:
	@test -n "$(PROJECT_ID)" || { echo "usage: make teardown PROJECT_ID=<gcp-project>"; exit 1; }
	bash infra/teardown.sh $(PROJECT_ID) $(GCP_REGION) $(GCP_REGION_B) $(BUCKET) $(JOB_NAME) $(SCHEDULER_NAME)

kill-mid-run:
	bash infra/kill_mid_run.sh
