"""
mcp-server/main.py
FastAPI application that hosts the MCP server over SSE transport.
Run: uvicorn main:app --host 0.0.0.0 --port 8001
"""

from __future__ import annotations

import logging
import sys

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from mcp.server import FastMCP
from mcp.server.sse import SseServerTransport

from tools.snowflake_tools import register_snowflake_tools

# ── Logging ───────────────────────────────────────────────────────────────────
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s — %(message)s",
    stream=sys.stdout,
)
logger = logging.getLogger("mcp-server")

# ── MCP setup ─────────────────────────────────────────────────────────────────
mcp = FastMCP(
    name="snowflake-mcp",
    description="MCP server exposing Snowflake query tools to AI agents.",
    version="1.0.0",
)

register_snowflake_tools(mcp)

# ── FastAPI app ────────────────────────────────────────────────────────────────
app = FastAPI(
    title="Snowflake MCP Server",
    version="1.0.0",
    description="Model Context Protocol server backed by Snowflake.",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],   # tighten in production
    allow_methods=["*"],
    allow_headers=["*"],
)

# Mount the MCP SSE transport at /sse
sse_transport = SseServerTransport("/sse")
app.mount("/sse", sse_transport.get_asgi_app(mcp))


@app.get("/health")
async def health() -> dict:
    return {"status": "ok", "service": "snowflake-mcp"}


@app.get("/tools")
async def list_tools() -> dict:
    """List registered MCP tool names (debug endpoint)."""
    tool_names = [t.name for t in mcp.list_tools()]
    return {"tools": tool_names}
