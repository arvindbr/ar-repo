"""
agent/agent.py
Attribution AI Agent — OpenAI Agents SDK wired to the Attribution MCP Server.
The agent can answer marketing attribution questions in natural language.
"""

from __future__ import annotations

import logging
from typing import Any

from agents import Agent, MCPServerSse, Runner, gen_trace_id, trace
from agents.mcp import MCPServerSseParams

from shared.config import get_mcp_settings, get_openai_settings

logger = logging.getLogger(__name__)

# ── System prompt ──────────────────────────────────────────────────────────────

ATTRIBUTION_SYSTEM_PROMPT = """\
You are an expert marketing attribution analyst with deep knowledge of
multi-touch attribution modelling, channel performance analysis, and
marketing ROI measurement.

You have access to a suite of attribution analysis tools backed by Snowflake:

ATTRIBUTION MODELS
──────────────────
• get_attribution          — Run a single attribution model (first/last/linear/
                             time_decay/position_based/data_driven)
• compare_attribution_models — Compare all six models side-by-side

CHANNEL PERFORMANCE
───────────────────
• get_channel_performance  — Sessions, conversions, revenue by channel/campaign
• get_channel_roas         — ROAS and CPA per channel
• get_spend_trend          — Spend over time by channel
• get_top_campaigns        — Best-performing campaigns by any metric

CONVERSION PATHS
────────────────
• get_top_conversion_paths      — Most common channel sequences before conversion
• get_path_length_distribution  — Distribution of journey lengths
• get_assisted_conversions      — Assisted vs. direct conversions per channel
• get_time_to_conversion        — Time-to-convert statistics (avg, median, p90)

COHORT & INCREMENTALITY
────────────────────────
• get_cohort_conversion_rate    — Conversion rates by acquisition cohort
• get_channel_overlap           — Pairwise channel co-occurrence (synergy)
• get_new_vs_returning_attribution — Attribution split by new vs. returning users

GUIDELINES
──────────
- Always clarify the attribution model being used in your answer.
- When the user doesn't specify a model, use "linear" as the default and
  mention that other models are available.
- For ROAS questions, always call get_channel_roas alongside get_channel_performance
  to give the full picture.
- When comparing channels, offer to run compare_attribution_models to show
  how results shift across models — different models tell very different stories.
- Summarise numbers in plain language first, then show tables.
- Round monetary values to 2 decimal places and conversion rates to 1 decimal place.
- Default date range: current quarter unless the user specifies otherwise.
- If results are empty, suggest broadening the date range or checking that the
  conversion event name is correct.
"""


def build_mcp_server() -> MCPServerSse:
    cfg = get_mcp_settings()
    return MCPServerSse(
        params=MCPServerSseParams(url=cfg.server_url),
        name="attribution-mcp",
        cache_tools_list=True,
    )


def build_agent(mcp_server: MCPServerSse) -> Agent:
    openai_cfg = get_openai_settings()
    return Agent(
        name="AttributionAnalystAgent",
        instructions=ATTRIBUTION_SYSTEM_PROMPT,
        model=openai_cfg.model,
        mcp_servers=[mcp_server],
    )


async def run_agent(user_message: str) -> dict[str, Any]:
    """
    Run one turn of the Attribution Agent.

    Returns:
        {
          "final_output": str,
          "trace_id":     str,
          "tool_calls":   list[str],
        }
    """
    trace_id = gen_trace_id()
    logger.info("Attribution agent run. trace_id=%s msg=%s", trace_id, user_message[:100])

    mcp_server = build_mcp_server()
    agent = build_agent(mcp_server)

    async with mcp_server:
        with trace("attribution-agent-run", trace_id=trace_id):
            result = await Runner.run(agent, input=user_message)

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
