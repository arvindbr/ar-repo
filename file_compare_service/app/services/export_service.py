"""
app/services/export_service.py
Export diff results to CSV or multi-sheet Excel workbook.
"""
from __future__ import annotations

import io
import logging

import pandas as pd

from app.config import get_settings
from app.models.schemas import DiffRow, DiffStats, DiffType

logger   = logging.getLogger(__name__)
settings = get_settings()


# ── helpers ───────────────────────────────────────────────────────────────────

def _diff_rows_to_dataframe(diff_rows: list[DiffRow]) -> pd.DataFrame:
    records = []
    for r in diff_rows[:settings.export_max_rows]:
        base: dict = {
            "diff_type":    r.diff_type.value,
            "row_index_a":  r.row_index_a,
            "row_index_b":  r.row_index_b,
        }
        if r.key_values:
            for k, v in r.key_values.items():
                base[f"key_{k}"] = v
        if r.changes:
            for chg in r.changes:
                base[f"{chg.column}_A"] = chg.value_a
                base[f"{chg.column}_B"] = chg.value_b
        elif r.row_a:
            for k, v in r.row_a.items():
                base[f"{k}_A"] = v
        elif r.row_b:
            for k, v in r.row_b.items():
                base[f"{k}_B"] = v
        records.append(base)
    return pd.DataFrame(records)


def _stats_to_dataframe(stats: DiffStats) -> pd.DataFrame:
    rows = [
        ("File A total rows",    stats.total_rows_a,    ""),
        ("File B total rows",    stats.total_rows_b,    ""),
        ("Unchanged rows",       stats.rows_matched,    f"{stats.pct_unchanged}%"),
        ("Rows only in A",       stats.rows_only_in_a,  f"{stats.pct_removed}%"),
        ("Rows only in B",       stats.rows_only_in_b,  f"{stats.pct_added}%"),
        ("Modified rows",        stats.rows_modified,   f"{stats.pct_modified}%"),
        ("Columns added (B)",    ", ".join(stats.columns_added)   or "—", ""),
        ("Columns removed (B)",  ", ".join(stats.columns_removed) or "—", ""),
    ]
    return pd.DataFrame(rows, columns=["Metric", "Value", "Percentage"])


def _col_changes_to_dataframe(stats: DiffStats) -> pd.DataFrame:
    return pd.DataFrame(
        [{"Column": cs.column, "Changes": cs.change_count, "Change %": cs.change_pct}
         for cs in stats.column_change_counts]
    )


# ── public exports ─────────────────────────────────────────────────────────────

def export_csv(diff_rows: list[DiffRow]) -> bytes:
    """Return a UTF-8 CSV byte string of all diff rows."""
    df = _diff_rows_to_dataframe(diff_rows)
    buf = io.StringIO()
    df.to_csv(buf, index=False)
    return buf.getvalue().encode("utf-8")


def export_excel(
    diff_rows: list[DiffRow],
    stats: DiffStats,
    ai_summary: str | None,
) -> bytes:
    """
    Return an Excel workbook bytes with 4 sheets:
      1. Summary Stats
      2. Column Changes
      3. Diff Detail (all diff_type rows except MATCHED)
      4. AI Narrative (if available)
    """
    buf = io.BytesIO()

    with pd.ExcelWriter(buf, engine="openpyxl") as writer:

        # Sheet 1 — Summary Stats
        _stats_to_dataframe(stats).to_excel(
            writer, sheet_name="Summary", index=False
        )

        # Sheet 2 — Column Changes
        col_df = _col_changes_to_dataframe(stats)
        if not col_df.empty:
            col_df.to_excel(writer, sheet_name="Column Changes", index=False)

        # Sheet 3 — Diff Detail (exclude MATCHED to keep size manageable)
        non_matched = [r for r in diff_rows if r.diff_type != DiffType.MATCHED]
        detail_df   = _diff_rows_to_dataframe(non_matched)
        if not detail_df.empty:
            detail_df.to_excel(writer, sheet_name="Diff Detail", index=False)

        # Sheet 4 — AI Summary
        if ai_summary:
            pd.DataFrame([{"AI Narrative Summary": ai_summary}]).to_excel(
                writer, sheet_name="AI Summary", index=False
            )

        # Auto-fit column widths
        for sheet in writer.sheets.values():
            for col_cells in sheet.columns:
                max_len = max(
                    (len(str(cell.value)) for cell in col_cells if cell.value), default=10
                )
                sheet.column_dimensions[col_cells[0].column_letter].width = min(max_len + 4, 60)

    buf.seek(0)
    return buf.read()
