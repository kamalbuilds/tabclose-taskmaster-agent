PY ?= $(if $(wildcard ../../.venv/bin/python),../../.venv/bin/python,python3)
export PYTHONPATH := .:../shared

TARGET_URL ?= http://localhost:8080/health
GCP_REGION ?= us-central1
GCP_REGION_B ?= europe-west1

.PHONY: deploy demo demo-live tick test teardown

test:
	$(PY) -m pytest . -v

demo:
	$(PY) demo_local.py

demo-live:
	TABCLOSE_TARGET_URL=$(TARGET_URL) $(PY) -m job.main

tick: demo-live

deploy:
	@test -n "$(PROJECT_ID)" || { echo "usage: make deploy PROJECT_ID=<gcp-project>"; exit 1; }
	PROJECT_ID=$(PROJECT_ID) REGION=$(GCP_REGION) REGION_B=$(GCP_REGION_B) bash ../../infra/deploy_tabclose.sh

teardown:
	@test -n "$(PROJECT_ID)" || { echo "usage: make teardown PROJECT_ID=<gcp-project>"; exit 1; }
	PROJECT_ID=$(PROJECT_ID) REGION=$(GCP_REGION) REGION_B=$(GCP_REGION_B) PROJECTS=tabclose bash ../../infra/teardown.sh

kill-mid-run:
	bash infra/kill_mid_run.sh
