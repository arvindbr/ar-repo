# ── AI Agent — OpenAI Agents SDK ──────────────────────────
FROM python:3.12-slim AS base

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1

WORKDIR /app

# ── Dependencies ──────────────────────────────────────────
COPY agent/requirements.txt ./
RUN pip install --upgrade pip && pip install -r requirements.txt

# ── App source ────────────────────────────────────────────
COPY shared/ ./shared/
COPY agent/ ./

EXPOSE 8000

HEALTHCHECK --interval=30s --timeout=5s --start-period=10s \
  CMD curl -f http://localhost:8000/health || exit 1

CMD ["uvicorn", "main:app", "--host", "0.0.0.0", "--port", "8000"]
