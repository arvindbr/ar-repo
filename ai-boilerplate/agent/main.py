"""
agent/main.py
FastAPI wrapper around the OpenAI agent.
Run: uvicorn main:app --host 0.0.0.0 --port 8000
"""

from __future__ import annotations

import logging
import sys

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel

from agent import run_agent

# ── Logging ───────────────────────────────────────────────────────────────────
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s — %(message)s",
    stream=sys.stdout,
)
logger = logging.getLogger("agent-api")

# ── FastAPI app ────────────────────────────────────────────────────────────────
app = FastAPI(
    title="AI Data Analyst Agent",
    version="1.0.0",
    description="OpenAI Agents SDK agent backed by MCP + Snowflake.",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],   # tighten in production
    allow_methods=["*"],
    allow_headers=["*"],
)


# ── Request / response models ──────────────────────────────────────────────────

class QueryRequest(BaseModel):
    message: str
    """Natural language question to send to the agent."""


class QueryResponse(BaseModel):
    answer: str
    trace_id: str
    tool_calls: list[str]


# ── Routes ─────────────────────────────────────────────────────────────────────

@app.get("/health")
async def health() -> dict:
    return {"status": "ok", "service": "agent-api"}


@app.post("/query", response_model=QueryResponse)
async def query(req: QueryRequest) -> QueryResponse:
    """
    Send a natural language question to the AI agent.
    The agent will call Snowflake via the MCP server and return an answer.
    """
    if not req.message.strip():
        raise HTTPException(status_code=400, detail="message must not be empty")

    logger.info("Received query: %s", req.message[:200])

    try:
        result = await run_agent(req.message)
    except Exception as exc:
        logger.exception("Agent run failed")
        raise HTTPException(status_code=500, detail=str(exc)) from exc

    return QueryResponse(
        answer=result["final_output"],
        trace_id=result["trace_id"],
        tool_calls=result["tool_calls"],
    )
