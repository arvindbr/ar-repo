"""
app/services/diff_service.py
Core file comparison logic.
Supports key-based (MERGE) and positional (row-by-row) diffing.
Handles large files via chunked processing.
"""
from __future__ import annotations

import hashlib
import logging
from typing import Iterator

import pandas as pd

from app.config import get_settings
from app.models.schemas import (
    ColumnChange, ColumnStats, DiffRow, DiffStats, DiffType,
)
from app.utils.file_utils import normalise_dataframe

logger  = logging.getLogger(__name__)
settings = get_settings()

MAX_PREVIEW = settings.max_preview_rows


# ── helpers ───────────────────────────────────────────────────────────────────

def _row_hash(row: pd.Series) -> str:
    """SHA-1 fingerprint of a row's concatenated values."""
    payload = "|".join(str(v) for v in row.values)
    return hashlib.sha1(payload.encode()).hexdigest()


def _schema_diff(cols_a: list[str], cols_b: list[str]) -> tuple[list[str], list[str]]:
    set_a, set_b = set(cols_a), set(cols_b)
    return sorted(set_b - set_a), sorted(set_a - set_b)   # added, removed


def _column_change_counts(modified_rows: list[DiffRow], cols: list[str]) -> list[ColumnStats]:
    counts: dict[str, int] = {c: 0 for c in cols}
    total = len(modified_rows)
    for row in modified_rows:
        if row.changes:
            for chg in row.changes:
                counts[chg.column] = counts.get(chg.column, 0) + 1
    return [
        ColumnStats(
            column=col,
            change_count=cnt,
            change_pct=round(cnt / total * 100, 2) if total else 0.0,
        )
        for col, cnt in sorted(counts.items(), key=lambda x: -x[1])
        if cnt > 0
    ]


# ── key-based diff ────────────────────────────────────────────────────────────

def _key_based_diff(
    df_a: pd.DataFrame,
    df_b: pd.DataFrame,
    key_columns: list[str],
    include_matched: bool,
) -> tuple[list[DiffRow], int, int, int, int]:
    """
    Outer-merge on key columns, identify ONLY_IN_A / ONLY_IN_B / MODIFIED / MATCHED.
    Returns (diff_rows, only_a_count, only_b_count, modified_count, matched_count).
    """
    suffix_a, suffix_b = "_FILE_A", "_FILE_B"

    # Build key string for merge
    def make_key(df: pd.DataFrame) -> pd.Series:
        return df[key_columns].astype(str).agg("|".join, axis=1)

    df_a = df_a.copy()
    df_b = df_b.copy()
    df_a["__key__"] = make_key(df_a)
    df_b["__key__"] = make_key(df_b)

    merged = pd.merge(
        df_a, df_b,
        on="__key__",
        how="outer",
        suffixes=(suffix_a, suffix_b),
        indicator=True,
    )

    diff_rows:    list[DiffRow] = []
    only_a = only_b = modified = matched = 0

    # Common value columns (exclude keys and merge indicator)
    value_cols_a = [c for c in df_a.columns if c not in key_columns + ["__key__"]]
    value_cols_b = [c for c in df_b.columns if c not in key_columns + ["__key__"]]
    common_value_cols = [c for c in value_cols_a if c in value_cols_b]

    for idx, row in merged.iterrows():
        indicator = row["_merge"]
        key_vals  = {k: row.get(k + suffix_a) or row.get(k + suffix_b) for k in key_columns}

        if indicator == "left_only":
            only_a += 1
            diff_rows.append(DiffRow(
                diff_type=DiffType.ONLY_IN_A,
                key_values=key_vals,
                row_a={c: row.get(c + suffix_a) for c in value_cols_a},
            ))

        elif indicator == "right_only":
            only_b += 1
            diff_rows.append(DiffRow(
                diff_type=DiffType.ONLY_IN_B,
                key_values=key_vals,
                row_b={c: row.get(c + suffix_b) for c in value_cols_b},
            ))

        else:
            # Both sides present — check for value changes
            changes = []
            for col in common_value_cols:
                va = row.get(col + suffix_a)
                vb = row.get(col + suffix_b)
                if str(va) != str(vb):
                    changes.append(ColumnChange(column=col, value_a=va, value_b=vb))

            if changes:
                modified += 1
                diff_rows.append(DiffRow(
                    diff_type=DiffType.MODIFIED,
                    key_values=key_vals,
                    changes=changes,
                    row_a={c: row.get(c + suffix_a) for c in value_cols_a},
                    row_b={c: row.get(c + suffix_b) for c in value_cols_b},
                ))
            else:
                matched += 1
                if include_matched:
                    diff_rows.append(DiffRow(
                        diff_type=DiffType.MATCHED,
                        key_values=key_vals,
                    ))

    return diff_rows, only_a, only_b, modified, matched


# ── positional diff ───────────────────────────────────────────────────────────

def _positional_diff(
    df_a: pd.DataFrame,
    df_b: pd.DataFrame,
    include_matched: bool,
) -> tuple[list[DiffRow], int, int, int, int]:
    """
    Row-by-row comparison when no key columns are specified.
    Uses SHA-1 hash to detect changes; handles unequal row counts.
    """
    hashes_a = df_a.apply(_row_hash, axis=1).tolist()
    hashes_b = df_b.apply(_row_hash, axis=1).tolist()

    max_rows = max(len(hashes_a), len(hashes_b))
    diff_rows: list[DiffRow] = []
    only_a = only_b = modified = matched = 0

    common_cols = [c for c in df_a.columns if c in df_b.columns]

    for i in range(max_rows):
        in_a = i < len(hashes_a)
        in_b = i < len(hashes_b)

        if in_a and not in_b:
            only_a += 1
            diff_rows.append(DiffRow(
                row_index_a=i,
                diff_type=DiffType.ONLY_IN_A,
                row_a=df_a.iloc[i].to_dict(),
            ))
        elif in_b and not in_a:
            only_b += 1
            diff_rows.append(DiffRow(
                row_index_b=i,
                diff_type=DiffType.ONLY_IN_B,
                row_b=df_b.iloc[i].to_dict(),
            ))
        elif hashes_a[i] != hashes_b[i]:
            modified += 1
            changes = [
                ColumnChange(
                    column=col,
                    value_a=df_a.iloc[i][col],
                    value_b=df_b.iloc[i][col],
                )
                for col in common_cols
                if str(df_a.iloc[i][col]) != str(df_b.iloc[i][col])
            ]
            diff_rows.append(DiffRow(
                row_index_a=i,
                row_index_b=i,
                diff_type=DiffType.MODIFIED,
                changes=changes,
                row_a=df_a.iloc[i].to_dict(),
                row_b=df_b.iloc[i].to_dict(),
            ))
        else:
            matched += 1
            if include_matched:
                diff_rows.append(DiffRow(
                    row_index_a=i,
                    row_index_b=i,
                    diff_type=DiffType.MATCHED,
                ))

    return diff_rows, only_a, only_b, modified, matched


# ── public entry point ────────────────────────────────────────────────────────

def compare_dataframes(
    df_a: pd.DataFrame,
    df_b: pd.DataFrame,
    key_columns:     list[str] | None,
    ignore_columns:  list[str] | None,
    case_sensitive:  bool,
    trim_whitespace: bool,
    include_matched: bool,
) -> tuple[DiffStats, list[DiffRow]]:
    """
    Full comparison pipeline.
    Returns (DiffStats, list[DiffRow]).
    diff_rows is capped at MAX_PREVIEW rows for the JSON response;
    the caller stores the full list for export.
    """
    # Schema diff (before normalisation so we report original column names)
    cols_added, cols_removed = _schema_diff(list(df_a.columns), list(df_b.columns))

    # Normalise
    df_a_n = normalise_dataframe(df_a, trim_whitespace, case_sensitive, ignore_columns)
    df_b_n = normalise_dataframe(df_b, trim_whitespace, case_sensitive, ignore_columns)

    total_a = len(df_a_n)
    total_b = len(df_b_n)

    if key_columns:
        missing = [k for k in key_columns if k not in df_a_n.columns or k not in df_b_n.columns]
        if missing:
            raise ValueError(f"Key column(s) not found in one or both files: {missing}")
        all_rows, only_a, only_b, modified, matched = _key_based_diff(
            df_a_n, df_b_n, key_columns, include_matched
        )
    else:
        all_rows, only_a, only_b, modified, matched = _positional_diff(
            df_a_n, df_b_n, include_matched
        )

    modified_rows = [r for r in all_rows if r.diff_type == DiffType.MODIFIED]
    common_cols   = [c for c in df_a_n.columns if c in df_b_n.columns
                     and c not in (key_columns or [])]

    stats = DiffStats(
        total_rows_a=total_a,
        total_rows_b=total_b,
        rows_only_in_a=only_a,
        rows_only_in_b=only_b,
        rows_matched=matched,
        rows_modified=modified,
        pct_unchanged=round(matched   / max(total_a, 1) * 100, 2),
        pct_removed  =round(only_a    / max(total_a, 1) * 100, 2),
        pct_added    =round(only_b    / max(total_b, 1) * 100, 2),
        pct_modified =round(modified  / max(total_a, 1) * 100, 2),
        columns_in_a =list(df_a.columns),
        columns_in_b =list(df_b.columns),
        columns_added=cols_added,
        columns_removed=cols_removed,
        column_change_counts=_column_change_counts(modified_rows, common_cols),
    )

    return stats, all_rows
