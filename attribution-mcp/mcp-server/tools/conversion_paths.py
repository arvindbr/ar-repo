"""
mcp-server/tools/conversion_paths.py
Conversion path analysis — top paths, path length distribution,
assisted conversions, and funnel drop-off.
"""

from __future__ import annotations

import logging
from typing import Any

from mcp.server import FastMCP

from shared.config import get_attribution_settings
from tools._db import run_query

logger = logging.getLogger(__name__)


def register_conversion_path_tools(mcp: FastMCP) -> None:

    @mcp.tool()
    def get_top_conversion_paths(
        start_date: str,
        end_date: str,
        conversion_event: str = "purchase",
        lookback_days: int | None = None,
        limit: int = 20,
    ) -> list[dict[str, Any]]:
        """
        Return the most common channel sequences that lead to a conversion.
        Paths are represented as channel1 > channel2 > ... > channelN.

        Args:
            start_date:       ISO date string
            end_date:         ISO date string
            conversion_event: Conversion event type (default: "purchase")
            lookback_days:    Touchpoint lookback window in days
            limit:            Max number of paths to return (max 100)

        Returns:
            List of {path, path_length, conversions, total_value} rows.
        """
        cfg = get_attribution_settings()
        lbd = lookback_days or cfg.default_lookback_days
        limit = min(int(limit), 100)

        sql = f"""
            WITH conversions AS (
                SELECT user_id, conversion_id, conversion_value, converted_at
                FROM {cfg.conversions_table}
                WHERE converted_at BETWEEN %(start_date)s AND %(end_date)s
                  AND conversion_event = %(event)s
            ),
            ordered_touches AS (
                SELECT
                    c.conversion_id,
                    c.conversion_value,
                    LISTAGG(t.channel, ' > ')
                        WITHIN GROUP (ORDER BY t.touched_at ASC) AS path,
                    COUNT(t.touchpoint_id)                        AS path_length
                FROM conversions c
                JOIN {cfg.touchpoints_table} t
                  ON t.user_id = c.user_id
                 AND t.touched_at BETWEEN
                       DATEADD('day', -%(lookback)s, c.converted_at)
                       AND c.converted_at
                GROUP BY c.conversion_id, c.conversion_value
            )
            SELECT
                path,
                path_length,
                COUNT(*)           AS conversions,
                SUM(conversion_value) AS total_value,
                AVG(conversion_value) AS avg_value
            FROM ordered_touches
            GROUP BY path, path_length
            ORDER BY conversions DESC
            LIMIT {limit}
        """
        logger.info("get_top_conversion_paths %s→%s event=%s", start_date, end_date, conversion_event)
        return run_query(sql, {
            "start_date": start_date, "end_date": end_date,
            "event": conversion_event, "lookback": lbd,
        })

    @mcp.tool()
    def get_path_length_distribution(
        start_date: str,
        end_date: str,
        conversion_event: str = "purchase",
        lookback_days: int | None = None,
    ) -> list[dict[str, Any]]:
        """
        Return the distribution of journey lengths (number of touchpoints)
        before conversion — useful for understanding buyer complexity.

        Args:
            start_date:       ISO date string
            end_date:         ISO date string
            conversion_event: Conversion event type (default: "purchase")
            lookback_days:    Touchpoint lookback window in days

        Returns:
            List of {path_length, conversions, pct_of_total} rows.
        """
        cfg = get_attribution_settings()
        lbd = lookback_days or cfg.default_lookback_days

        sql = f"""
            WITH conversions AS (
                SELECT user_id, conversion_id, converted_at
                FROM {cfg.conversions_table}
                WHERE converted_at BETWEEN %(start_date)s AND %(end_date)s
                  AND conversion_event = %(event)s
            ),
            lengths AS (
                SELECT
                    c.conversion_id,
                    COUNT(t.touchpoint_id) AS path_length
                FROM conversions c
                JOIN {cfg.touchpoints_table} t
                  ON t.user_id = c.user_id
                 AND t.touched_at BETWEEN
                       DATEADD('day', -%(lookback)s, c.converted_at)
                       AND c.converted_at
                GROUP BY c.conversion_id
            )
            SELECT
                path_length,
                COUNT(*)                                         AS conversions,
                ROUND(COUNT(*) * 100.0 / SUM(COUNT(*)) OVER (), 2) AS pct_of_total
            FROM lengths
            GROUP BY path_length
            ORDER BY path_length
        """
        logger.info("get_path_length_distribution %s→%s", start_date, end_date)
        return run_query(sql, {
            "start_date": start_date, "end_date": end_date,
            "event": conversion_event, "lookback": lbd,
        })

    @mcp.tool()
    def get_assisted_conversions(
        start_date: str,
        end_date: str,
        conversion_event: str = "purchase",
        lookback_days: int | None = None,
    ) -> list[dict[str, Any]]:
        """
        For each channel, return how many conversions it assisted (appeared in
        the journey but was NOT the last touch) vs. how many it directly closed.

        Args:
            start_date:       ISO date string
            end_date:         ISO date string
            conversion_event: Conversion event type (default: "purchase")
            lookback_days:    Touchpoint lookback window in days

        Returns:
            List of {channel, assisted_conversions, direct_conversions,
                     assist_ratio} rows sorted by assisted_conversions desc.
        """
        cfg = get_attribution_settings()
        lbd = lookback_days or cfg.default_lookback_days

        sql = f"""
            WITH conversions AS (
                SELECT user_id, conversion_id, converted_at
                FROM {cfg.conversions_table}
                WHERE converted_at BETWEEN %(start_date)s AND %(end_date)s
                  AND conversion_event = %(event)s
            ),
            ranked AS (
                SELECT
                    t.channel,
                    c.conversion_id,
                    ROW_NUMBER() OVER (
                        PARTITION BY c.conversion_id ORDER BY t.touched_at DESC
                    ) AS recency_rank
                FROM conversions c
                JOIN {cfg.touchpoints_table} t
                  ON t.user_id = c.user_id
                 AND t.touched_at BETWEEN
                       DATEADD('day', -%(lookback)s, c.converted_at)
                       AND c.converted_at
            )
            SELECT
                channel,
                COUNT(CASE WHEN recency_rank  > 1 THEN 1 END) AS assisted_conversions,
                COUNT(CASE WHEN recency_rank  = 1 THEN 1 END) AS direct_conversions,
                ROUND(
                    COUNT(CASE WHEN recency_rank > 1 THEN 1 END)::FLOAT
                    / NULLIF(COUNT(CASE WHEN recency_rank = 1 THEN 1 END), 0),
                    2
                ) AS assist_ratio
            FROM ranked
            GROUP BY channel
            ORDER BY assisted_conversions DESC
        """
        logger.info("get_assisted_conversions %s→%s", start_date, end_date)
        return run_query(sql, {
            "start_date": start_date, "end_date": end_date,
            "event": conversion_event, "lookback": lbd,
        })

    @mcp.tool()
    def get_time_to_conversion(
        start_date: str,
        end_date: str,
        conversion_event: str = "purchase",
        lookback_days: int | None = None,
    ) -> dict[str, Any]:
        """
        Return statistics on how long (in hours/days) it takes users to convert
        from their first touchpoint.

        Args:
            start_date:       ISO date string
            end_date:         ISO date string
            conversion_event: Conversion event type (default: "purchase")
            lookback_days:    Touchpoint lookback window in days

        Returns:
            Dict with avg, median, p25, p75, p90 time-to-conversion in hours.
        """
        cfg = get_attribution_settings()
        lbd = lookback_days or cfg.default_lookback_days

        sql = f"""
            WITH conversions AS (
                SELECT user_id, conversion_id, converted_at
                FROM {cfg.conversions_table}
                WHERE converted_at BETWEEN %(start_date)s AND %(end_date)s
                  AND conversion_event = %(event)s
            ),
            first_touch AS (
                SELECT
                    c.conversion_id,
                    DATEDIFF('hour', MIN(t.touched_at), c.converted_at)
                        AS hours_to_convert
                FROM conversions c
                JOIN {cfg.touchpoints_table} t
                  ON t.user_id = c.user_id
                 AND t.touched_at BETWEEN
                       DATEADD('day', -%(lookback)s, c.converted_at)
                       AND c.converted_at
                GROUP BY c.conversion_id, c.converted_at
            )
            SELECT
                ROUND(AVG(hours_to_convert), 1)                        AS avg_hours,
                ROUND(MEDIAN(hours_to_convert), 1)                     AS median_hours,
                ROUND(PERCENTILE_CONT(0.25) WITHIN GROUP
                    (ORDER BY hours_to_convert), 1)                    AS p25_hours,
                ROUND(PERCENTILE_CONT(0.75) WITHIN GROUP
                    (ORDER BY hours_to_convert), 1)                    AS p75_hours,
                ROUND(PERCENTILE_CONT(0.90) WITHIN GROUP
                    (ORDER BY hours_to_convert), 1)                    AS p90_hours,
                COUNT(*)                                               AS total_conversions
            FROM first_touch
        """
        logger.info("get_time_to_conversion %s→%s", start_date, end_date)
        rows = run_query(sql, {
            "start_date": start_date, "end_date": end_date,
            "event": conversion_event, "lookback": lbd,
        })
        return rows[0] if rows else {}
