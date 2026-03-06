# ============================================================
# CortexDB - Consciousness-Inspired Unified Database
# Production Dockerfile
# (c) 2026 Nirlab Inc.
# ============================================================

FROM python:3.12-slim AS base

LABEL maintainer="Nirlab Inc <eng@nirlab.ai>"
LABEL description="CortexDB - One database to replace them all"
LABEL version="4.0.0"

RUN groupadd -r cortex && useradd -r -g cortex cortex

RUN apt-get update && apt-get install -y --no-install-recommends \
    curl \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY src/cortexdb/ ./cortexdb/

RUN mkdir -p /data/immutable /data/cache && \
    chown -R cortex:cortex /data /app

USER cortex

HEALTHCHECK --interval=5s --timeout=3s --start-period=10s --retries=3 \
    CMD curl -f http://localhost:5401/health/live || exit 1

EXPOSE 5400 5401 5402

CMD ["uvicorn", "cortexdb.server:app", "--host", "0.0.0.0", "--port", "5400", "--workers", "2"]
