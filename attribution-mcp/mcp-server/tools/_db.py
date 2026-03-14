"""
mcp-server/tools/_db.py
Thin Snowflake connection helper — imported by all attribution tool modules.
"""

from __future__ import annotations

from contextlib import contextmanager
from typing import Any

import snowflake.connector

from shared.config import get_snowflake_settings


@contextmanager
def get_connection():
    """Yield an open Snowflake DictCursor-capable connection."""
    cfg = get_snowflake_settings()
    conn = snowflake.connector.connect(
        account=cfg.account,
        user=cfg.user,
        password=cfg.password.get_secret_value(),
        warehouse=cfg.warehouse,
        database=cfg.database,
        schema=cfg.schema_,
        role=cfg.role,
        session_parameters={"QUERY_TAG": "attribution-mcp"},
    )
    try:
        yield conn
    finally:
        conn.close()


def run_query(sql: str, params: tuple = ()) -> list[dict[str, Any]]:
    """Execute *sql* with optional *params* and return rows as dicts."""
    with get_connection() as conn:
        cur = conn.cursor(snowflake.connector.DictCursor)
        cur.execute(sql, params)
        return cur.fetchall()


def run_scalar(sql: str, params: tuple = ()) -> Any:
    """Return the first cell of the first row."""
    rows = run_query(sql, params)
    if not rows:
        return None
    return next(iter(rows[0].values()))
