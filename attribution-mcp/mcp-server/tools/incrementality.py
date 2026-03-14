"""
mcp-server/tools/incrementality.py
Cohort analysis and incrementality / lift measurement tools.
"""

from __future__ import annotations

import logging
from typing import Any

from mcp.server import FastMCP

from shared.config import get_attribution_settings
from tools._db import run_query

logger = logging.getLogger(__name__)


def register_incrementality_tools(mcp: FastMCP) -> None:

    @mcp.tool()
    def get_cohort_conversion_rate(
        cohort_start: str,
        cohort_end: str,
        conversion_event: str = "purchase",
        observation_days: int = 30,
    ) -> list[dict[str, Any]]:
        """
        Return conversion rates for user cohorts acquired in a date range,
        observed over a fixed window after acquisition.

        Args:
            cohort_start:     First acquisition date (ISO), e.g. "2024-01-01"
            cohort_end:       Last acquisition date (ISO),  e.g. "2024-01-31"
            conversion_event: Conversion event to track (default: "purchase")
            observation_days: Days after first touch to observe conversion

        Returns:
            List of {cohort_week, channel, users, converters, conversion_rate} rows.
        """
        cfg = get_attribution_settings()
        sql = f"""
            WITH first_touches AS (
                SELECT
                    user_id,
                    channel,
                    DATE_TRUNC('week', MIN(touched_at)) AS cohort_week,
                    MIN(touched_at)                     AS first_touch_at
                FROM {cfg.touchpoints_table}
                WHERE touched_at BETWEEN %(cohort_start)s AND %(cohort_end)s
                GROUP BY user_id, channel
            ),
            conversions AS (
                SELECT DISTINCT user_id
                FROM {cfg.conversions_table}
                WHERE conversion_event = %(event)s
            )
            SELECT
                ft.cohort_week,
                ft.channel,
                COUNT(DISTINCT ft.user_id)              AS users,
                COUNT(DISTINCT c.user_id)               AS converters,
                ROUND(
                    COUNT(DISTINCT c.user_id)::FLOAT
                    / NULLIF(COUNT(DISTINCT ft.user_id), 0) * 100, 2
                )                                       AS conversion_rate_pct
            FROM first_touches ft
            LEFT JOIN {cfg.conversions_table} conv
              ON ft.user_id = conv.user_id
             AND conv.conversion_event = %(event)s
             AND conv.converted_at BETWEEN ft.first_touch_at
                   AND DATEADD('day', %(obs_days)s, ft.first_touch_at)
            LEFT JOIN conversions c ON ft.user_id = c.user_id
            GROUP BY ft.cohort_week, ft.channel
            ORDER BY ft.cohort_week, ft.channel
        """
        logger.info("get_cohort_conversion_rate %s→%s", cohort_start, cohort_end)
        return run_query(sql, {
            "cohort_start": cohort_start,
            "cohort_end": cohort_end,
            "event": conversion_event,
            "obs_days": observation_days,
        })

    @mcp.tool()
    def get_channel_overlap(
        start_date: str,
        end_date: str,
    ) -> list[dict[str, Any]]:
        """
        Return pairwise channel overlap — how often users are exposed to
        both channel A and channel B in the same journey.
        Useful for understanding channel synergy.

        Args:
            start_date: ISO date string
            end_date:   ISO date string

        Returns:
            List of {channel_a, channel_b, shared_users, overlap_pct} rows.
        """
        cfg = get_attribution_settings()
        sql = f"""
            WITH user_channels AS (
                SELECT DISTINCT user_id, channel
                FROM {cfg.touchpoints_table}
                WHERE touched_at BETWEEN %(start_date)s AND %(end_date)s
            ),
            total_per_channel AS (
                SELECT channel, COUNT(DISTINCT user_id) AS total_users
                FROM user_channels
                GROUP BY channel
            )
            SELECT
                a.channel  AS channel_a,
                b.channel  AS channel_b,
                COUNT(DISTINCT a.user_id)          AS shared_users,
                ROUND(
                    COUNT(DISTINCT a.user_id)::FLOAT
                    / NULLIF(ta.total_users, 0) * 100, 2
                )                                  AS pct_of_channel_a_users
            FROM user_channels a
            JOIN user_channels b
              ON a.user_id = b.user_id AND a.channel < b.channel
            JOIN total_per_channel ta ON a.channel = ta.channel
            GROUP BY a.channel, b.channel, ta.total_users
            ORDER BY shared_users DESC
        """
        logger.info("get_channel_overlap %s→%s", start_date, end_date)
        return run_query(sql, {"start_date": start_date, "end_date": end_date})

    @mcp.tool()
    def get_new_vs_returning_attribution(
        start_date: str,
        end_date: str,
        conversion_event: str = "purchase",
    ) -> list[dict[str, Any]]:
        """
        Break down attributed conversions and value by channel AND user type
        (new vs. returning) to understand acquisition vs. retention efficiency.

        Args:
            start_date:       ISO date string
            end_date:         ISO date string
            conversion_event: Conversion event type (default: "purchase")

        Returns:
            List of {channel, user_type, conversions, revenue} rows.
        """
        cfg = get_attribution_settings()
        sql = f"""
            WITH first_conversion AS (
                SELECT
                    user_id,
                    MIN(converted_at) AS first_conversion_at
                FROM {cfg.conversions_table}
                WHERE conversion_event = %(event)s
                GROUP BY user_id
            ),
            conversions_labeled AS (
                SELECT
                    c.user_id,
                    c.conversion_id,
                    c.conversion_value,
                    c.converted_at,
                    CASE WHEN c.converted_at = fc.first_conversion_at
                         THEN 'new' ELSE 'returning' END AS user_type
                FROM {cfg.conversions_table} c
                JOIN first_conversion fc USING (user_id)
                WHERE c.converted_at BETWEEN %(start_date)s AND %(end_date)s
                  AND c.conversion_event = %(event)s
            )
            SELECT
                t.channel,
                cl.user_type,
                COUNT(DISTINCT cl.conversion_id) AS conversions,
                SUM(cl.conversion_value)         AS revenue,
                AVG(cl.conversion_value)         AS avg_order_value
            FROM conversions_labeled cl
            JOIN {cfg.touchpoints_table} t
              ON cl.user_id = t.user_id
             AND t.touched_at <= cl.converted_at
            GROUP BY t.channel, cl.user_type
            ORDER BY t.channel, cl.user_type
        """
        logger.info("get_new_vs_returning_attribution %s→%s", start_date, end_date)
        return run_query(sql, {
            "start_date": start_date,
            "end_date": end_date,
            "event": conversion_event,
        })
