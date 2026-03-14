"""
agent/agent.py
OpenAI Agents SDK agent wired to the MCP server.
The agent discovers all tools exposed by the MCP server at runtime.
"""

from __future__ import annotations

import logging
from typing import Any

from agents import Agent, MCPServerSse, Runner, gen_trace_id, trace
from agents.mcp import MCPServerSseParams

from shared.config import get_mcp_settings, get_openai_settings

logger = logging.getLogger(__name__)


# ── System prompt ──────────────────────────────────────────────────────────────

SYSTEM_PROMPT = """\
You are a helpful data analyst assistant with access to a Snowflake data warehouse.

You can:
- Execute SQL SELECT queries against Snowflake
- List available tables and describe their schemas
- Answer business questions by querying the data

Guidelines:
- Always prefer parameterised or safe queries.
- Summarise query results in plain language before showing raw data.
- If a query returns more than 20 rows, show a condensed summary unless asked otherwise.
- Never modify data (no INSERT / UPDATE / DELETE / DROP).
"""


# ── Agent factory ──────────────────────────────────────────────────────────────

def build_mcp_server() -> MCPServerSse:
    """Construct the MCP SSE server connection."""
    cfg = get_mcp_settings()
    return MCPServerSse(
        params=MCPServerSseParams(url=cfg.server_url),
        name="snowflake-mcp",
        cache_tools_list=True,    # cache tool discovery between requests
    )


def build_agent(mcp_server: MCPServerSse) -> Agent:
    """Build the OpenAI agent with the MCP server attached."""
    openai_cfg = get_openai_settings()
    return Agent(
        name="DataAnalystAgent",
        instructions=SYSTEM_PROMPT,
        model=openai_cfg.model,
        mcp_servers=[mcp_server],
    )


async def run_agent(user_message: str) -> dict[str, Any]:
    """
    Run one turn of the agent and return the result.

    Args:
        user_message: Natural language question or instruction from the user.

    Returns:
        Dict with keys:
            - final_output  (str)  — agent's final answer
            - trace_id      (str)  — trace ID for debugging
            - tool_calls    (list) — names of tools invoked
    """
    trace_id = gen_trace_id()
    logger.info("Agent run started. trace_id=%s", trace_id)

    mcp_server = build_mcp_server()
    agent = build_agent(mcp_server)

    async with mcp_server:
        with trace("agent-run", trace_id=trace_id):
            result = await Runner.run(agent, input=user_message)

    # Collect tool calls from run steps
    tool_calls: list[str] = []
    for step in result.raw_responses or []:
        for choice in getattr(step, "choices", []):
            for tc in getattr(choice.message, "tool_calls", None) or []:
                tool_calls.append(tc.function.name)

    return {
        "final_output": result.final_output,
        "trace_id": trace_id,
        "tool_calls": tool_calls,
    }
