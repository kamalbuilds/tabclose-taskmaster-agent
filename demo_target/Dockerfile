# Cloud Run *Service* for the demo target (this one is a normal HTTP
# service, not a Job -- it's the tiny thing we own that Tabclose watches).
#
# Build context is THIS repo root: `docker build -f demo_target/Dockerfile .`

FROM python:3.12-slim

WORKDIR /app

COPY demo_target/requirements.txt /app/requirements.txt
RUN pip install --no-cache-dir -r /app/requirements.txt

COPY demo_target/app.py /app/app.py

ENV PYTHONUNBUFFERED=1
ENV PORT=8080
EXPOSE 8080

CMD ["python", "app.py"]
