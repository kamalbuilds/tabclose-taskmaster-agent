# Cloud Run Job image for the tabclose tick.
#
# Build context MUST be the devpost/ repo root (not projects/tabclose/),
# because this image also needs projects/shared/agentspine. infra/deploy.sh
# invokes `gcloud builds submit` with the correct context and -f flag; see
# that script for the exact command.

FROM python:3.12-slim

WORKDIR /app

COPY projects/shared/pyproject.toml /app/shared/pyproject.toml
COPY projects/shared/agentspine /app/shared/agentspine
RUN pip install --no-cache-dir /app/shared

COPY projects/tabclose/job/requirements.txt /app/tabclose/job/requirements.txt
RUN pip install --no-cache-dir -r /app/tabclose/job/requirements.txt

COPY projects/tabclose/agent /app/tabclose/agent
COPY projects/tabclose/validator /app/tabclose/validator
COPY projects/tabclose/probes /app/tabclose/probes
COPY projects/tabclose/job /app/tabclose/job

WORKDIR /app/tabclose
ENV PYTHONUNBUFFERED=1

ENTRYPOINT ["python", "-m", "job.main"]
