"""
agent/main.py
FastAPI wrapper for the Attribution AI Agent.
Run: uvicorn main:app --host 0.0.0.0 --port 8000
"""

from __future__ import annotations

import logging
import sys
from typing import Literal

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field

from agent import run_agent

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s — %(message)s",
    stream=sys.stdout,
)
logger = logging.getLogger("attribution-agent-api")

app = FastAPI(
    title="Attribution AI Agent API",
    version="1.0.0",
    description=(
        "Natural language interface to the Attribution MCP Server. "
        "Ask marketing attribution questions in plain English."
    ),
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)


# ── Models ─────────────────────────────────────────────────────────────────────

class QueryRequest(BaseModel):
    message: str = Field(..., description="Natural language attribution question")
    context: dict | None = Field(
        None,
        description="Optional structured context (date_range, channel, model, etc.)",
        examples=[{"date_range": "2024-Q1", "model": "linear"}],
    )


class QueryResponse(BaseModel):
    answer:     str
    trace_id:   str
    tool_calls: list[str]


# ── Routes ─────────────────────────────────────────────────────────────────────

@app.get("/health")
async def health() -> dict:
    return {"status": "ok", "service": "attribution-agent-api"}


@app.post("/query", response_model=QueryResponse)
async def query(req: QueryRequest) -> QueryResponse:
    """
    Send a natural language attribution question to the AI agent.

    Example questions:
    - "Which channel has the highest ROAS in Q1 2024?"
    - "Show me the top 10 conversion paths last month."
    - "Compare first-touch vs linear attribution for paid social."
    - "How long does it take users from Instagram to convert?"
    - "Which channels are assisting the most conversions but not getting credit?"
    """
    if not req.message.strip():
        raise HTTPException(status_code=400, detail="message must not be empty")

    # Optionally inject structured context into the message
    full_message = req.message
    if req.context:
        context_str = ", ".join(f"{k}: {v}" for k, v in req.context.items())
        full_message = f"{req.message}\n\n[Context: {context_str}]"

    logger.info("Query received: %s", full_message[:200])

    try:
        result = await run_agent(full_message)
    except Exception as exc:
        logger.exception("Agent run failed")
        raise HTTPException(status_code=500, detail=str(exc)) from exc

    return QueryResponse(
        answer=result["final_output"],
        trace_id=result["trace_id"],
        tool_calls=result["tool_calls"],
    )


@app.get("/examples")
async def example_questions() -> dict:
    """Return example attribution questions to help users get started."""
    return {
        "examples": [
            "Which channel has the best ROAS this quarter?",
            "Show me the top 10 conversion paths in January 2024.",
            "Compare all attribution models for the purchase event in Q4 2023.",
            "What percentage of Google Ads conversions were assisted by email?",
            "How long does it take for paid social users to convert?",
            "Which two channels have the most user overlap?",
            "Break down conversions by new vs returning users per channel.",
            "Show me weekly spend trend for paid_search over the last 3 months.",
            "Which campaigns have the highest conversion rate?",
            "What is the average order value by acquisition channel?",
        ]
    }
