# ── MCP Server — Snowflake backend ────────────────────────
FROM python:3.12-slim AS base

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1

WORKDIR /app

# System deps for snowflake connector
RUN apt-get update && apt-get install -y --no-install-recommends \
    gcc libssl-dev libffi-dev && \
    rm -rf /var/lib/apt/lists/*

# ── Dependencies ──────────────────────────────────────────
COPY mcp-server/requirements.txt ./
RUN pip install --upgrade pip && pip install -r requirements.txt

# ── App source ────────────────────────────────────────────
COPY shared/ ./shared/
COPY mcp-server/ ./

EXPOSE 8001

HEALTHCHECK --interval=30s --timeout=5s --start-period=10s \
  CMD curl -f http://localhost:8001/health || exit 1

CMD ["uvicorn", "main:app", "--host", "0.0.0.0", "--port", "8001"]
