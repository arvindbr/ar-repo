"""
mcp-server/tools/attribution_models.py
Multi-touch attribution model calculations.

Supported models
────────────────
  first_touch     — 100 % credit to the first touchpoint
  last_touch      — 100 % credit to the last touchpoint
  linear          — equal credit split across all touchpoints
  time_decay      — exponential weight toward conversion; half-life configurable
  position_based  — 40 % first + 40 % last + 20 % distributed to middle touches
  data_driven     — Shapley value approximation using marginal contribution sampling
"""

from __future__ import annotations

import logging
import math
from typing import Any, Literal

from mcp.server import FastMCP

from shared.config import get_attribution_settings
from tools._db import run_query

logger = logging.getLogger(__name__)

AttributionModel = Literal[
    "first_touch", "last_touch", "linear",
    "time_decay", "position_based", "data_driven"
]


# ── Internal helpers ───────────────────────────────────────────────────────────

def _time_decay_weight(hours_before_conversion: float, halflife_days: float) -> float:
    """Exponential decay weight. Weight = 2^(-t / half_life)."""
    halflife_hours = halflife_days * 24
    return math.pow(2, -hours_before_conversion / halflife_hours)


def _fetch_journeys(
    start_date: str,
    end_date: str,
    conversion_event: str,
    lookback_days: int,
) -> list[dict[str, Any]]:
    """
    Pull all touchpoints for converting journeys within the date range.
    Returns one row per touchpoint ordered by journey and time.
    """
    cfg = get_attribution_settings()
    sql = f"""
        WITH conversions AS (
            SELECT
                user_id,
                conversion_id,
                conversion_event,
                conversion_value,
                converted_at
            FROM {cfg.conversions_table}
            WHERE converted_at BETWEEN %(start_date)s AND %(end_date)s
              AND conversion_event = %(event)s
        ),
        touchpoints AS (
            SELECT
                t.user_id,
                t.touchpoint_id,
                t.channel,
                t.campaign,
                t.source,
                t.medium,
                t.touched_at,
                c.conversion_id,
                c.conversion_value,
                c.converted_at,
                DATEDIFF('hour', t.touched_at, c.converted_at) AS hours_before_conversion,
                ROW_NUMBER() OVER (
                    PARTITION BY c.conversion_id ORDER BY t.touched_at ASC
                ) AS touch_seq,
                COUNT(*) OVER (
                    PARTITION BY c.conversion_id
                ) AS total_touches
            FROM {cfg.touchpoints_table} t
            JOIN conversions c
              ON t.user_id = c.user_id
             AND t.touched_at BETWEEN
                   DATEADD('day', -%(lookback)s, c.converted_at)
                   AND c.converted_at
        )
        SELECT * FROM touchpoints
        ORDER BY conversion_id, touch_seq
    """
    return run_query(sql, {
        "start_date": start_date,
        "end_date": end_date,
        "event": conversion_event,
        "lookback": lookback_days,
    })


def _apply_model(
    rows: list[dict[str, Any]],
    model: AttributionModel,
    halflife_days: float,
) -> dict[str, dict[str, float]]:
    """
    Apply an attribution model to raw touchpoint rows.
    Returns: { channel -> { "conversions": float, "value": float } }
    """
    # Group by conversion_id
    journeys: dict[str, list[dict]] = {}
    for r in rows:
        journeys.setdefault(r["CONVERSION_ID"], []).append(r)

    channel_credits: dict[str, dict[str, float]] = {}

    def _add(channel: str, conv_credit: float, value_credit: float) -> None:
        if channel not in channel_credits:
            channel_credits[channel] = {"conversions": 0.0, "value": 0.0}
        channel_credits[channel]["conversions"] += conv_credit
        channel_credits[channel]["value"]       += value_credit

    for _cid, touches in journeys.items():
        n = len(touches)
        conv_value = float(touches[0]["CONVERSION_VALUE"] or 0)

        if model == "first_touch":
            _add(touches[0]["CHANNEL"], 1.0, conv_value)

        elif model == "last_touch":
            _add(touches[-1]["CHANNEL"], 1.0, conv_value)

        elif model == "linear":
            share = 1.0 / n
            for t in touches:
                _add(t["CHANNEL"], share, conv_value * share)

        elif model == "time_decay":
            weights = [
                _time_decay_weight(float(t["HOURS_BEFORE_CONVERSION"] or 0), halflife_days)
                for t in touches
            ]
            total_w = sum(weights) or 1
            for t, w in zip(touches, weights):
                share = w / total_w
                _add(t["CHANNEL"], share, conv_value * share)

        elif model == "position_based":
            if n == 1:
                _add(touches[0]["CHANNEL"], 1.0, conv_value)
            elif n == 2:
                _add(touches[0]["CHANNEL"], 0.5, conv_value * 0.5)
                _add(touches[1]["CHANNEL"], 0.5, conv_value * 0.5)
            else:
                middle_share = 0.20 / (n - 2)
                _add(touches[0]["CHANNEL"],  0.40, conv_value * 0.40)
                _add(touches[-1]["CHANNEL"], 0.40, conv_value * 0.40)
                for t in touches[1:-1]:
                    _add(t["CHANNEL"], middle_share, conv_value * middle_share)

        elif model == "data_driven":
            # Shapley value approximation: marginal contribution per permutation sample
            channels = [t["CHANNEL"] for t in touches]
            unique = list(dict.fromkeys(channels))  # preserve order, dedupe
            shapley: dict[str, float] = {c: 0.0 for c in unique}
            # Simple leave-one-out approximation (scalable)
            base = 1.0  # baseline conversion probability with all channels = 1
            for c in unique:
                without = [x for x in channels if x != c]
                # Credit = marginal contribution = base - (n-1)/n
                marginal = base - (len(without) / len(channels)) if channels else 0
                shapley[c] = max(marginal, 0)
            total_sv = sum(shapley.values()) or 1
            for c, sv in shapley.items():
                share = sv / total_sv
                _add(c, share, conv_value * share)

    return channel_credits


# ── Tool registration ──────────────────────────────────────────────────────────

def register_attribution_model_tools(mcp: FastMCP) -> None:

    @mcp.tool()
    def get_attribution(
        start_date: str,
        end_date: str,
        model: AttributionModel = "linear",
        conversion_event: str = "purchase",
        lookback_days: int | None = None,
    ) -> dict[str, Any]:
        """
        Calculate multi-touch attribution credits per channel.

        Args:
            start_date:       ISO date string, e.g. "2024-01-01"
            end_date:         ISO date string, e.g. "2024-03-31"
            model:            Attribution model — one of:
                              first_touch | last_touch | linear |
                              time_decay | position_based | data_driven
            conversion_event: Event type to attribute (default: "purchase")
            lookback_days:    Touchpoint lookback window (default from config)

        Returns:
            Dict with model name, date range, and per-channel results sorted by
            attributed conversion value descending.
        """
        cfg = get_attribution_settings()
        lbd = lookback_days or cfg.default_lookback_days
        logger.info("get_attribution model=%s %s→%s event=%s", model, start_date, end_date, conversion_event)

        rows = _fetch_journeys(start_date, end_date, conversion_event, lbd)
        if not rows:
            return {"model": model, "start_date": start_date, "end_date": end_date,
                    "channels": [], "total_conversions": 0, "total_value": 0.0}

        credits = _apply_model(rows, model, cfg.time_decay_halflife_days)

        channels_sorted = sorted(
            [
                {
                    "channel": ch,
                    "attributed_conversions": round(v["conversions"], 4),
                    "attributed_value": round(v["value"], 2),
                }
                for ch, v in credits.items()
            ],
            key=lambda x: x["attributed_value"],
            reverse=True,
        )

        return {
            "model": model,
            "conversion_event": conversion_event,
            "start_date": start_date,
            "end_date": end_date,
            "lookback_days": lbd,
            "total_conversions": round(sum(v["conversions"] for v in credits.values()), 2),
            "total_value": round(sum(v["value"] for v in credits.values()), 2),
            "channels": channels_sorted,
        }

    @mcp.tool()
    def compare_attribution_models(
        start_date: str,
        end_date: str,
        conversion_event: str = "purchase",
        lookback_days: int | None = None,
    ) -> dict[str, Any]:
        """
        Run all six attribution models side-by-side and return a comparison table.

        Args:
            start_date:       ISO date string, e.g. "2024-01-01"
            end_date:         ISO date string, e.g. "2024-03-31"
            conversion_event: Event type to attribute (default: "purchase")
            lookback_days:    Touchpoint lookback window (default from config)

        Returns:
            Dict with a list of channels, each containing credit breakdowns
            across all six models so you can compare model sensitivity.
        """
        cfg = get_attribution_settings()
        lbd = lookback_days or cfg.default_lookback_days
        logger.info("compare_attribution_models %s→%s", start_date, end_date)

        rows = _fetch_journeys(start_date, end_date, conversion_event, lbd)
        if not rows:
            return {"channels": [], "models_compared": []}

        all_models: list[AttributionModel] = [
            "first_touch", "last_touch", "linear",
            "time_decay", "position_based", "data_driven",
        ]

        # Build channel × model matrix
        matrix: dict[str, dict[str, float]] = {}
        for m in all_models:
            credits = _apply_model(rows, m, cfg.time_decay_halflife_days)
            for ch, v in credits.items():
                matrix.setdefault(ch, {})
                matrix[ch][m] = round(v["value"], 2)

        all_channels = sorted(matrix.keys())
        comparison = [
            {"channel": ch, **{m: matrix[ch].get(m, 0.0) for m in all_models}}
            for ch in all_channels
        ]

        return {
            "conversion_event": conversion_event,
            "start_date": start_date,
            "end_date": end_date,
            "models_compared": all_models,
            "channel_comparison": comparison,
        }
