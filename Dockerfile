FROM python:3.10-slim

RUN apt-get update && rm -rf /var/lib/apt/lists/*

WORKDIR /app
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt \
    && playwright install chromium \
    && playwright install-deps chromium

COPY triage/ ./triage/
COPY cv_adapter/ ./cv_adapter/
COPY tests/ ./tests/
