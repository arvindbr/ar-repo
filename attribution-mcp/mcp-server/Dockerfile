FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1 PIP_NO_CACHE_DIR=1

WORKDIR /app

RUN apt-get update && apt-get install -y --no-install-recommends \
    gcc libssl-dev libffi-dev curl && rm -rf /var/lib/apt/lists/*

COPY mcp-server/requirements.txt ./
RUN pip install --upgrade pip && pip install -r requirements.txt

COPY shared/ ./shared/
COPY mcp-server/ ./

EXPOSE 8001

HEALTHCHECK --interval=30s --timeout=5s --start-period=15s \
  CMD curl -f http://localhost:8001/health || exit 1

CMD ["uvicorn", "main:app", "--host", "0.0.0.0", "--port", "8001"]
