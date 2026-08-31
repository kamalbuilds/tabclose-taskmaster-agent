# Cloud Run Job image for the tabclose tick.
#
# Build context is THIS repo root (projects/tabclose/ when viewed from the
# monorepo, or simply `.` in the standalone submission repo). The repo
# vendors agentspine, so no sibling directory is needed and
# `docker build -f job/Dockerfile .` works from a clean clone.
#
# NOTE: requirements.txt is intentionally lean (Vercel 'Try it out' only).
# The full Cloud Run dep set is in requirements-cloudrun.txt and installed
# here via pyproject.toml (which pins the same versions).

FROM python:3.12-slim

WORKDIR /app

# Install dependencies first so edits to source do not bust the layer cache.
COPY pyproject.toml /app/pyproject.toml
COPY requirements-cloudrun.txt /app/requirements-cloudrun.txt
COPY agentspine /app/agentspine
COPY agent /app/agent
COPY validator /app/validator
COPY probes /app/probes
COPY job /app/job

RUN pip install --no-cache-dir -r requirements-cloudrun.txt && pip install --no-cache-dir --no-deps .

ENV PYTHONUNBUFFERED=1

ENTRYPOINT ["python", "-m", "job.main"]
