"""
tests/test_compare.py
Unit tests for the diff service and file utilities.
Covers: delimited files, fixed-width files, diff modes, edge cases.
"""
from __future__ import annotations

import io
import textwrap
import pytest
import pandas as pd

from app.services.diff_service import compare_dataframes
from app.utils.file_utils import (
    detect_delimiter, detect_encoding, read_dataframe,
    detect_fixed_width_columns, _read_fixed_width,
)
from app.models.schemas import (
    DiffType, FileFormat, FileReference, FixedWidthColumn,
)


# ── Fixtures ──────────────────────────────────────────────────────────────────

def make_csv(rows: list[dict]) -> bytes:
    df  = pd.DataFrame(rows)
    buf = io.StringIO()
    df.to_csv(buf, index=False)
    return buf.getvalue().encode("utf-8")


def make_fixed_width(rows: list[str], header_rows: list[str] | None = None) -> bytes:
    """Build a fixed-width file as bytes from pre-formatted row strings."""
    lines = (header_rows or []) + rows
    return "\n".join(lines).encode("utf-8")


# ── Sample column specs ───────────────────────────────────────────────────────

FW_COLS = [
    FixedWidthColumn(name="cusip",  start=0,  end=10),
    FixedWidthColumn(name="ccy",    start=10, end=13),
    FixedWidthColumn(name="price",  start=13, end=23),
    FixedWidthColumn(name="status", start=23, end=30),
]

FW_ROW_1 = "TELA000001USD 100.5000ACTIVE "
FW_ROW_2 = "APPL000002USD 200.0000ACTIVE "
FW_ROW_3 = "MSFT000003EUR  99.9900CLOSED "


# ── file_utils — delimited ────────────────────────────────────────────────────

def test_detect_delimiter_comma():
    assert detect_delimiter(b"a,b,c\n1,2,3\n", "utf-8") == ","

def test_detect_delimiter_pipe():
    assert detect_delimiter(b"a|b|c\n1|2|3\n", "utf-8") == "|"

def test_detect_delimiter_tab():
    assert detect_delimiter(b"a\tb\tc\n1\t2\t3\n", "utf-8") == "\t"

def test_detect_delimiter_semicolon():
    assert detect_delimiter(b"a;b;c\n1;2;3\n", "utf-8") == ";"

def test_read_delimited_basic():
    raw = make_csv([{"id": 1, "name": "Alice"}, {"id": 2, "name": "Bob"}])
    ref = FileReference(container="c", blob_path="f.csv", file_format=FileFormat.DELIMITED)
    df  = read_dataframe(raw, file_ref=ref)
    assert list(df.columns) == ["id", "name"]
    assert len(df) == 2

def test_read_delimited_no_header():
    raw = b"1,Alice\n2,Bob\n"
    ref = FileReference(container="c", blob_path="f.csv",
                        file_format=FileFormat.DELIMITED, has_header=False)
    df  = read_dataframe(raw, file_ref=ref)
    assert list(df.columns) == ["col_0", "col_1"]
    assert len(df) == 2

def test_read_delimited_pipe():
    raw = b"id|name\n1|Alice\n2|Bob\n"
    ref = FileReference(container="c", blob_path="f.psv",
                        file_format=FileFormat.DELIMITED, delimiter="|")
    df  = read_dataframe(raw, file_ref=ref)
    assert df.loc[0, "name"] == "Alice"


# ── file_utils — fixed-width ──────────────────────────────────────────────────

def test_read_fixed_width_basic():
    raw = make_fixed_width([FW_ROW_1, FW_ROW_2])
    df  = _read_fixed_width(
        raw_bytes=raw, encoding="utf-8", columns=FW_COLS,
        skip_header_rows=0, skip_footer_rows=0, comment_char=None, chunk_size=None,
    )
    assert list(df.columns) == ["cusip", "ccy", "price", "status"]
    assert len(df) == 2
    assert df.loc[0, "cusip"] == "TELA000001"
    assert df.loc[0, "ccy"]   == "USD"

def test_read_fixed_width_skip_header():
    raw = make_fixed_width(
        rows=[FW_ROW_1, FW_ROW_2],
        header_rows=["CUSIP     CCYPRICE    STATUS ", "---------- --- --------- -------"],
    )
    df = _read_fixed_width(
        raw_bytes=raw, encoding="utf-8", columns=FW_COLS,
        skip_header_rows=2, skip_footer_rows=0, comment_char=None, chunk_size=None,
    )
    assert len(df) == 2
    assert df.loc[0, "cusip"] == "TELA000001"

def test_read_fixed_width_skip_footer():
    raw = make_fixed_width(
        rows=[FW_ROW_1, FW_ROW_2, "TOTAL RECORDS: 2              "],
    )
    df = _read_fixed_width(
        raw_bytes=raw, encoding="utf-8", columns=FW_COLS,
        skip_header_rows=0, skip_footer_rows=1, comment_char=None, chunk_size=None,
    )
    assert len(df) == 2

def test_read_fixed_width_comment_lines():
    raw = make_fixed_width(rows=["# This is a comment", FW_ROW_1, FW_ROW_2])
    df  = _read_fixed_width(
        raw_bytes=raw, encoding="utf-8", columns=FW_COLS,
        skip_header_rows=0, skip_footer_rows=0, comment_char="#", chunk_size=None,
    )
    assert len(df) == 2

def test_read_fixed_width_via_file_ref():
    raw = make_fixed_width([FW_ROW_1, FW_ROW_2, FW_ROW_3])
    ref = FileReference(
        container="c", blob_path="prices.dat",
        file_format=FileFormat.FIXED_WIDTH,
        columns=FW_COLS,
    )
    df = read_dataframe(raw, file_ref=ref)
    assert len(df) == 3
    assert df.loc[2, "ccy"] == "EUR"

def test_fixed_width_auto_detect_columns():
    # Well-separated fixed-width: auto-detection should find 3 fields
    raw = b"AAA   BBB   CCC  \nDDD   EEE   FFF  \n"
    cols = detect_fixed_width_columns(raw, "utf-8")
    assert len(cols) >= 3

def test_fixed_width_validation_end_before_start():
    with pytest.raises(ValueError, match="end.*must be"):
        FixedWidthColumn(name="bad", start=10, end=5)

def test_fixed_width_missing_columns_raises():
    with pytest.raises(ValueError, match="columns is required"):
        FileReference(
            container="c", blob_path="f.dat",
            file_format=FileFormat.FIXED_WIDTH,
            columns=None,
        )


# ── diff_service — positional ─────────────────────────────────────────────────

def _compare(rows_a, rows_b, keys=None, **kwargs):
    df_a = pd.DataFrame(rows_a).astype(str)
    df_b = pd.DataFrame(rows_b).astype(str)
    return compare_dataframes(
        df_a, df_b,
        key_columns     = keys,
        ignore_columns  = None,
        case_sensitive  = True,
        trim_whitespace = True,
        include_matched = kwargs.get("include_matched", False),
    )

def test_identical_files():
    data = [{"id": "1", "val": "a"}, {"id": "2", "val": "b"}]
    stats, rows = _compare(data, data)
    assert stats.rows_matched   == 2
    assert stats.rows_only_in_a == 0
    assert stats.rows_only_in_b == 0
    assert stats.rows_modified  == 0

def test_row_added():
    a = [{"id": "1", "val": "a"}]
    b = [{"id": "1", "val": "a"}, {"id": "2", "val": "b"}]
    stats, rows = _compare(a, b)
    assert stats.rows_only_in_b == 1

def test_row_removed():
    a = [{"id": "1", "val": "a"}, {"id": "2", "val": "b"}]
    b = [{"id": "1", "val": "a"}]
    stats, rows = _compare(a, b)
    assert stats.rows_only_in_a == 1

def test_row_modified_positional():
    a = [{"id": "1", "val": "old"}]
    b = [{"id": "1", "val": "new"}]
    stats, rows = _compare(a, b)
    assert stats.rows_modified == 1
    mod = [r for r in rows if r.diff_type == DiffType.MODIFIED][0]
    assert any(c.column == "val" for c in mod.changes)


# ── diff_service — key-based ──────────────────────────────────────────────────

def test_key_based_modified():
    a = [{"id": "1", "price": "100.00"}, {"id": "2", "price": "200.00"}]
    b = [{"id": "1", "price": "105.00"}, {"id": "2", "price": "200.00"}]
    stats, rows = _compare(a, b, keys=["id"])
    assert stats.rows_modified == 1
    assert stats.rows_matched  == 1

def test_key_based_added_and_removed():
    a = [{"id": "1", "val": "x"}, {"id": "2", "val": "y"}]
    b = [{"id": "1", "val": "x"}, {"id": "3", "val": "z"}]
    stats, rows = _compare(a, b, keys=["id"])
    assert stats.rows_only_in_a == 1
    assert stats.rows_only_in_b == 1
    assert stats.rows_matched   == 1

def test_ignore_columns():
    a = [{"id": "1", "val": "a", "ts": "2024-01-01"}]
    b = [{"id": "1", "val": "a", "ts": "2026-01-01"}]
    df_a = pd.DataFrame(a).astype(str)
    df_b = pd.DataFrame(b).astype(str)
    stats, rows = compare_dataframes(
        df_a, df_b, key_columns=["id"], ignore_columns=["ts"],
        case_sensitive=True, trim_whitespace=True, include_matched=False,
    )
    assert stats.rows_matched  == 1
    assert stats.rows_modified == 0

def test_trim_whitespace():
    a = [{"id": "1", "val": "  hello  "}]
    b = [{"id": "1", "val": "hello"}]
    stats, rows = _compare(a, b, keys=["id"])
    assert stats.rows_matched  == 1
    assert stats.rows_modified == 0

def test_schema_diff_detected():
    a = [{"id": "1", "col_a": "x"}]
    b = [{"id": "1", "col_b": "y"}]
    stats, _ = _compare(a, b)
    assert "col_b" in stats.columns_added


# ── diff_service — fixed-width end-to-end ────────────────────────────────────

def test_fixed_width_diff_end_to_end():
    """Parse two fixed-width files and diff them by key column."""
    raw_a = make_fixed_width([FW_ROW_1, FW_ROW_2])
    raw_b = make_fixed_width([
        "TELA000001USD 105.5000ACTIVE ",   # price changed
        "APPL000002USD 200.0000ACTIVE ",   # unchanged
    ])
    ref = FileReference(
        container="c", blob_path="f.dat",
        file_format=FileFormat.FIXED_WIDTH, columns=FW_COLS,
    )
    df_a = read_dataframe(raw_a, file_ref=ref)
    df_b = read_dataframe(raw_b, file_ref=ref)
    stats, rows = compare_dataframes(
        df_a, df_b,
        key_columns     = ["cusip"],
        ignore_columns  = None,
        case_sensitive  = True,
        trim_whitespace = True,
        include_matched = False,
    )
    assert stats.rows_modified == 1
    assert stats.rows_matched  == 1
    mod = [r for r in rows if r.diff_type == DiffType.MODIFIED][0]
    assert any(c.column == "price" for c in mod.changes)

def test_mixed_format_diff():
    """Compare a delimited file (A) against a fixed-width file (B)."""
    csv_rows = [{"cusip": "TELA000001", "ccy": "USD", "price": "100.5000", "status": "ACTIVE"}]
    raw_a = make_csv(csv_rows)
    raw_b = make_fixed_width([FW_ROW_1])

    ref_a = FileReference(container="c", blob_path="a.csv", file_format=FileFormat.DELIMITED)
    ref_b = FileReference(container="c", blob_path="b.dat",
                          file_format=FileFormat.FIXED_WIDTH, columns=FW_COLS)

    df_a = read_dataframe(raw_a, file_ref=ref_a)
    df_b = read_dataframe(raw_b, file_ref=ref_b)

    stats, rows = compare_dataframes(
        df_a, df_b,
        key_columns     = ["cusip"],
        ignore_columns  = None,
        case_sensitive  = True,
        trim_whitespace = True,
        include_matched = False,
    )
    # Same data → should match
    assert stats.rows_matched  == 1
    assert stats.rows_modified == 0
