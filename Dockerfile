# ============================================================
# CortexDB - AI Agent Data Infrastructure
# Intelligence Sidecar (Python Service)
# (c) 2026 Nirlab Inc.
# ============================================================

FROM python:3.12.2-slim AS base

LABEL maintainer="Nirlab Inc <eng@nirlab.ai>"
LABEL description="CortexDB intelligence sidecar — semantic cache, cross-engine queries, agent ops"
LABEL version="5.0.0"

RUN groupadd -r cortex && useradd -r -g cortex cortex

RUN apt-get update && apt-get install -y --no-install-recommends \
    curl \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY cortexdb/ ./cortexdb/
COPY src/cortexdb/ ./cortexdb/
COPY db/migrations/ ./db/migrations/

RUN mkdir -p /data/immutable /data/cache /data/superadmin && \
    chown -R cortex:cortex /data /app

ENV CORTEXDB_ROOT=/app
ENV CORTEXDB_DATA_DIR=/data/superadmin
ENV CORTEXDB_FORCE_MIGRATE=true

USER cortex

HEALTHCHECK --interval=5s --timeout=3s --start-period=10s --retries=3 \
    CMD curl -f http://localhost:5401/health/live || exit 1

EXPOSE 5400 5401 5402

CMD ["uvicorn", "cortexdb.server:app", "--host", "0.0.0.0", "--port", "5400", "--workers", "2"]
