"""
mcp-server/main.py
Attribution MCP Server — FastAPI + SSE transport.
Registers all attribution tool groups and exposes them over MCP.

Run: uvicorn main:app --host 0.0.0.0 --port 8001
"""

from __future__ import annotations

import logging
import sys

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from mcp.server import FastMCP
from mcp.server.sse import SseServerTransport

from tools.attribution_models    import register_attribution_model_tools
from tools.channel_performance   import register_channel_performance_tools
from tools.conversion_paths      import register_conversion_path_tools
from tools.incrementality        import register_incrementality_tools

# ── Logging ────────────────────────────────────────────────────────────────────
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s — %(message)s",
    stream=sys.stdout,
)
logger = logging.getLogger("attribution-mcp")

# ── MCP instance ───────────────────────────────────────────────────────────────
mcp = FastMCP(
    name="attribution-mcp",
    description=(
        "Multi-touch marketing attribution server. "
        "Provides channel performance, attribution modelling (first/last/linear/"
        "time-decay/position-based/data-driven), conversion path analysis, "
        "cohort analysis, and ROAS/ROI reporting — all backed by Snowflake."
    ),
    version="1.0.0",
)

# Register all tool groups
register_attribution_model_tools(mcp)
register_channel_performance_tools(mcp)
register_conversion_path_tools(mcp)
register_incrementality_tools(mcp)

logger.info("Registered %d MCP tools", len(mcp.list_tools()))

# ── FastAPI app ────────────────────────────────────────────────────────────────
app = FastAPI(
    title="Attribution MCP Server",
    version="1.0.0",
    description="MCP server for multi-touch marketing attribution analytics.",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

sse_transport = SseServerTransport("/sse")
app.mount("/sse", sse_transport.get_asgi_app(mcp))


@app.get("/health")
async def health() -> dict:
    return {"status": "ok", "service": "attribution-mcp"}


@app.get("/tools")
async def list_tools() -> dict:
    """List all registered MCP tool names."""
    return {
        "count": len(mcp.list_tools()),
        "tools": [
            {"name": t.name, "description": (t.description or "")[:120]}
            for t in mcp.list_tools()
        ],
    }
