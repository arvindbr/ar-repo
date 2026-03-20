"""
app/services/ai_service.py
Generate a plain-English executive summary of the diff using OpenAI.
"""
from __future__ import annotations

import logging

from openai import AsyncOpenAI
from tenacity import retry, stop_after_attempt, wait_exponential

from app.config import get_settings
from app.models.schemas import DiffStats

logger   = logging.getLogger(__name__)
settings = get_settings()


def _build_prompt(stats: DiffStats, file_a_name: str, file_b_name: str) -> str:
    col_changes = "\n".join(
        f"  - {cs.column}: {cs.change_count} rows changed ({cs.change_pct}%)"
        for cs in stats.column_change_counts[:10]   # top 10 columns
    ) or "  (no column-level changes detected)"

    schema_notes = []
    if stats.columns_added:
        schema_notes.append(f"Columns added in File B:   {', '.join(stats.columns_added)}")
    if stats.columns_removed:
        schema_notes.append(f"Columns removed in File B: {', '.join(stats.columns_removed)}")
    schema_section = "\n".join(schema_notes) or "No schema changes detected."

    return f"""You are a senior data quality analyst. 
Write a concise executive summary (4–6 sentences) comparing two data files for a business audience.
Be factual and precise. Highlight the most important findings. Flag any data quality concerns.

FILE COMPARISON REPORT
======================
File A : {file_a_name}
File B : {file_b_name}

ROW COUNTS
  File A total rows : {stats.total_rows_a:,}
  File B total rows : {stats.total_rows_b:,}

DIFF BREAKDOWN
  Unchanged rows    : {stats.rows_matched:,}  ({stats.pct_unchanged}%)
  Rows only in A    : {stats.rows_only_in_a:,}  ({stats.pct_removed}%)  — removed or missing
  Rows only in B    : {stats.rows_only_in_b:,}  ({stats.pct_added}%)    — added or new
  Modified rows     : {stats.rows_modified:,}  ({stats.pct_modified}%)  — same key, changed values

SCHEMA CHANGES
{schema_section}

TOP CHANGED COLUMNS
{col_changes}

Write your summary now:"""


@retry(
    stop=stop_after_attempt(3),
    wait=wait_exponential(multiplier=1, min=2, max=8),
    reraise=True,
)
async def generate_summary(
    stats: DiffStats,
    file_a_name: str,
    file_b_name: str,
) -> str:
    """Call OpenAI and return a narrative summary string."""
    if not settings.openai_api_key:
        return "AI summary unavailable: OPENAI_API_KEY not configured."

    client = AsyncOpenAI(api_key=settings.openai_api_key)
    prompt = _build_prompt(stats, file_a_name, file_b_name)

    try:
        response = await client.chat.completions.create(
            model=settings.openai_model,
            max_tokens=settings.openai_max_tokens,
            temperature=0.2,
            messages=[
                {
                    "role": "system",
                    "content": (
                        "You are a precise data quality analyst. "
                        "Respond only with the executive summary, no preamble or labels."
                    ),
                },
                {"role": "user", "content": prompt},
            ],
        )
        summary = response.choices[0].message.content.strip()
        logger.info("AI summary generated tokens_used=%d", response.usage.total_tokens)
        return summary

    except Exception as exc:
        logger.error("OpenAI call failed: %s", exc)
        return f"AI summary unavailable: {exc}"
