"""
mcp-server/tools/channel_performance.py
Channel-level performance, spend, ROAS, and ROI analysis tools.
"""

from __future__ import annotations

import logging
from typing import Any

from mcp.server import FastMCP

from shared.config import get_attribution_settings
from tools._db import run_query

logger = logging.getLogger(__name__)


def register_channel_performance_tools(mcp: FastMCP) -> None:

    @mcp.tool()
    def get_channel_performance(
        start_date: str,
        end_date: str,
        granularity: str = "channel",
    ) -> list[dict[str, Any]]:
        """
        Return impressions, clicks, sessions, conversions, and revenue
        broken down by channel (and optionally campaign or source).

        Args:
            start_date:   ISO date string, e.g. "2024-01-01"
            end_date:     ISO date string, e.g. "2024-03-31"
            granularity:  Breakdown level — "channel" | "campaign" | "source"

        Returns:
            List of performance rows sorted by revenue descending.
        """
        cfg = get_attribution_settings()
        group_col = {
            "channel":  "t.channel",
            "campaign": "t.campaign",
            "source":   "t.source",
        }.get(granularity, "t.channel")

        sql = f"""
            SELECT
                {group_col}                                  AS dimension,
                COUNT(DISTINCT t.session_id)                 AS sessions,
                COUNT(DISTINCT t.user_id)                    AS unique_users,
                COUNT(t.touchpoint_id)                       AS touchpoints,
                COUNT(DISTINCT c.conversion_id)              AS conversions,
                COALESCE(SUM(c.conversion_value), 0)         AS revenue,
                COALESCE(AVG(c.conversion_value), 0)         AS avg_order_value,
                CASE WHEN COUNT(DISTINCT t.session_id) > 0
                     THEN COUNT(DISTINCT c.conversion_id)::FLOAT
                          / COUNT(DISTINCT t.session_id)
                     ELSE 0 END                              AS conversion_rate
            FROM {cfg.touchpoints_table} t
            LEFT JOIN {cfg.conversions_table} c
              ON t.user_id = c.user_id
             AND c.converted_at BETWEEN %(start_date)s AND %(end_date)s
            WHERE t.touched_at BETWEEN %(start_date)s AND %(end_date)s
            GROUP BY 1
            ORDER BY revenue DESC
        """
        logger.info("get_channel_performance granularity=%s %s→%s", granularity, start_date, end_date)
        return run_query(sql, {"start_date": start_date, "end_date": end_date})

    @mcp.tool()
    def get_channel_roas(
        start_date: str,
        end_date: str,
    ) -> list[dict[str, Any]]:
        """
        Return ROAS (Return on Ad Spend) and CPA (Cost per Acquisition)
        per channel by joining spend data with attributed revenue.

        Args:
            start_date: ISO date string, e.g. "2024-01-01"
            end_date:   ISO date string, e.g. "2024-03-31"

        Returns:
            List of channel ROAS rows sorted by ROAS descending.
            Channels with zero spend are excluded.
        """
        cfg = get_attribution_settings()
        sql = f"""
            WITH spend AS (
                SELECT
                    channel,
                    SUM(spend_amount) AS total_spend
                FROM {cfg.spend_table}
                WHERE spend_date BETWEEN %(start_date)s AND %(end_date)s
                GROUP BY channel
            ),
            revenue AS (
                SELECT
                    t.channel,
                    COALESCE(SUM(c.conversion_value), 0) AS total_revenue,
                    COUNT(DISTINCT c.conversion_id)      AS conversions
                FROM {cfg.touchpoints_table} t
                LEFT JOIN {cfg.conversions_table} c
                  ON t.user_id = c.user_id
                 AND c.converted_at BETWEEN %(start_date)s AND %(end_date)s
                WHERE t.touched_at BETWEEN %(start_date)s AND %(end_date)s
                GROUP BY t.channel
            )
            SELECT
                s.channel,
                s.total_spend,
                COALESCE(r.total_revenue, 0)         AS total_revenue,
                COALESCE(r.conversions, 0)           AS conversions,
                CASE WHEN s.total_spend > 0
                     THEN r.total_revenue / s.total_spend
                     ELSE NULL END                   AS roas,
                CASE WHEN COALESCE(r.conversions, 0) > 0
                     THEN s.total_spend / r.conversions
                     ELSE NULL END                   AS cpa
            FROM spend s
            LEFT JOIN revenue r USING (channel)
            WHERE s.total_spend > 0
            ORDER BY roas DESC NULLS LAST
        """
        logger.info("get_channel_roas %s→%s", start_date, end_date)
        return run_query(sql, {"start_date": start_date, "end_date": end_date})

    @mcp.tool()
    def get_spend_trend(
        start_date: str,
        end_date: str,
        channel: str | None = None,
        period: str = "week",
    ) -> list[dict[str, Any]]:
        """
        Return spend trend over time, optionally filtered to a single channel.

        Args:
            start_date: ISO date string
            end_date:   ISO date string
            channel:    Filter to a specific channel name (optional)
            period:     Aggregation period — "day" | "week" | "month"

        Returns:
            List of {period_start, channel, spend} rows ordered by period_start.
        """
        cfg = get_attribution_settings()
        trunc_fn = {"day": "DAY", "week": "WEEK", "month": "MONTH"}.get(period, "WEEK")
        channel_filter = "AND channel = %(channel)s" if channel else ""

        sql = f"""
            SELECT
                DATE_TRUNC('{trunc_fn}', spend_date) AS period_start,
                channel,
                SUM(spend_amount)                    AS spend
            FROM {cfg.spend_table}
            WHERE spend_date BETWEEN %(start_date)s AND %(end_date)s
              {channel_filter}
            GROUP BY 1, 2
            ORDER BY 1, 2
        """
        params: dict = {"start_date": start_date, "end_date": end_date}
        if channel:
            params["channel"] = channel
        logger.info("get_spend_trend period=%s channel=%s", period, channel)
        return run_query(sql, params)

    @mcp.tool()
    def get_top_campaigns(
        start_date: str,
        end_date: str,
        limit: int = 10,
        metric: str = "revenue",
    ) -> list[dict[str, Any]]:
        """
        Return the top-performing campaigns ranked by a given metric.

        Args:
            start_date: ISO date string
            end_date:   ISO date string
            limit:      Number of campaigns to return (default 10, max 50)
            metric:     Ranking metric — "revenue" | "conversions" | "roas" | "sessions"

        Returns:
            List of campaign performance rows.
        """
        cfg = get_attribution_settings()
        limit = min(int(limit), 50)
        order_col = {
            "revenue":     "revenue",
            "conversions": "conversions",
            "roas":        "roas",
            "sessions":    "sessions",
        }.get(metric, "revenue")

        sql = f"""
            WITH campaign_perf AS (
                SELECT
                    t.channel,
                    t.campaign,
                    COUNT(DISTINCT t.session_id)            AS sessions,
                    COUNT(DISTINCT c.conversion_id)         AS conversions,
                    COALESCE(SUM(c.conversion_value), 0)    AS revenue
                FROM {cfg.touchpoints_table} t
                LEFT JOIN {cfg.conversions_table} c
                  ON t.user_id = c.user_id
                 AND c.converted_at BETWEEN %(start_date)s AND %(end_date)s
                WHERE t.touched_at BETWEEN %(start_date)s AND %(end_date)s
                GROUP BY t.channel, t.campaign
            ),
            with_spend AS (
                SELECT
                    p.*,
                    COALESCE(s.total_spend, 0)  AS spend,
                    CASE WHEN COALESCE(s.total_spend, 0) > 0
                         THEN p.revenue / s.total_spend
                         ELSE NULL END           AS roas
                FROM campaign_perf p
                LEFT JOIN (
                    SELECT campaign, SUM(spend_amount) AS total_spend
                    FROM {cfg.spend_table}
                    WHERE spend_date BETWEEN %(start_date)s AND %(end_date)s
                    GROUP BY campaign
                ) s USING (campaign)
            )
            SELECT * FROM with_spend
            ORDER BY {order_col} DESC NULLS LAST
            LIMIT {limit}
        """
        logger.info("get_top_campaigns metric=%s limit=%d", metric, limit)
        return run_query(sql, {"start_date": start_date, "end_date": end_date})
