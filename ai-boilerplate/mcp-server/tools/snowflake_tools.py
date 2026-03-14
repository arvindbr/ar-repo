"""
mcp-server/tools/snowflake_tools.py
MCP tool definitions that wrap Snowflake queries.
Each function decorated with @mcp.tool() becomes a callable tool
exposed over the MCP SSE transport.
"""

from __future__ import annotations

import logging
from contextlib import contextmanager
from typing import Any

import snowflake.connector
from mcp.server import FastMCP

from shared.config import get_snowflake_settings

logger = logging.getLogger(__name__)


# ── Connection helper ──────────────────────────────────────────────────────────

@contextmanager
def _get_connection():
    """Yield an open Snowflake connection, closing it afterwards."""
    cfg = get_snowflake_settings()
    conn = snowflake.connector.connect(
        account=cfg.account,
        user=cfg.user,
        password=cfg.password.get_secret_value(),
        warehouse=cfg.warehouse,
        database=cfg.database,
        schema=cfg.schema_,
        role=cfg.role,
        session_parameters={"QUERY_TAG": "mcp-server"},
    )
    try:
        yield conn
    finally:
        conn.close()


def _run_query(sql: str, params: tuple = ()) -> list[dict[str, Any]]:
    """Execute *sql* and return rows as a list of dicts."""
    with _get_connection() as conn:
        cur = conn.cursor(snowflake.connector.DictCursor)
        cur.execute(sql, params)
        return cur.fetchall()


# ── Tool registration ──────────────────────────────────────────────────────────

def register_snowflake_tools(mcp: FastMCP) -> None:
    """Register all Snowflake tools on the given FastMCP instance."""

    @mcp.tool()
    def run_sql(query: str) -> list[dict[str, Any]]:
        """
        Execute a read-only SQL query against Snowflake and return the results.

        Args:
            query: A valid Snowflake SQL SELECT statement.

        Returns:
            A list of row dicts, e.g. [{"COL_A": 1, "COL_B": "foo"}, ...].
        """
        # Safety: only allow SELECT / WITH / SHOW / DESCRIBE
        normalised = query.strip().upper()
        allowed_prefixes = ("SELECT", "WITH", "SHOW", "DESCRIBE", "DESC")
        if not any(normalised.startswith(p) for p in allowed_prefixes):
            raise ValueError(
                "Only SELECT / WITH / SHOW / DESCRIBE statements are permitted."
            )
        logger.info("run_sql: %s", query[:200])
        return _run_query(query)

    @mcp.tool()
    def list_tables(database: str | None = None, schema: str | None = None) -> list[dict]:
        """
        List all tables in a Snowflake database/schema.

        Args:
            database: Override the default database (optional).
            schema:   Override the default schema (optional).

        Returns:
            List of table metadata dicts.
        """
        cfg = get_snowflake_settings()
        db = database or cfg.database
        sc = schema or cfg.schema_
        sql = f"SHOW TABLES IN SCHEMA {db}.{sc}"
        logger.info("list_tables: %s.%s", db, sc)
        return _run_query(sql)

    @mcp.tool()
    def describe_table(table_name: str) -> list[dict]:
        """
        Return column-level metadata for a Snowflake table.

        Args:
            table_name: Fully-qualified (DB.SCHEMA.TABLE) or unqualified table name.

        Returns:
            List of column descriptor dicts with name, type, nullable, etc.
        """
        logger.info("describe_table: %s", table_name)
        return _run_query(f"DESCRIBE TABLE {table_name}")

    @mcp.tool()
    def get_row_count(table_name: str) -> dict[str, Any]:
        """
        Return the approximate row count for a Snowflake table.

        Args:
            table_name: Fully-qualified or unqualified table name.

        Returns:
            Dict with keys "table" and "row_count".
        """
        rows = _run_query(f"SELECT COUNT(*) AS ROW_COUNT FROM {table_name}")
        count = rows[0]["ROW_COUNT"] if rows else 0
        return {"table": table_name, "row_count": count}
