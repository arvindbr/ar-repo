"""
app/utils/file_utils.py
Unified file reader supporting:
  - Delimited files  (CSV, TSV, pipe, semicolon — auto-detected)
  - Fixed-width files (positional / mainframe-style flat files)

Public API
----------
read_dataframe(raw_bytes, file_ref, chunk_size)  → pd.DataFrame
normalise_dataframe(df, ...)                      → pd.DataFrame
detect_encoding(raw_bytes)                        → str
detect_delimiter(raw_bytes, encoding)             → str
detect_fixed_width_columns(raw_bytes, encoding)   → list[FixedWidthColumn]
"""
from __future__ import annotations

import csv
import io
import logging
import re
from typing import TYPE_CHECKING

import chardet
import pandas as pd

if TYPE_CHECKING:
    from app.models.schemas import FileReference, FixedWidthColumn

logger = logging.getLogger(__name__)

# Delimiter candidates tested in priority order
_DELIMITER_CANDIDATES = [",", "\t", "|", ";", ":"]


# =============================================================================
# Encoding detection
# =============================================================================

def detect_encoding(raw_bytes: bytes, sample_size: int = 65_536) -> str:
    """Detect file encoding from a byte sample. Falls back to utf-8."""
    sample = raw_bytes[:sample_size]
    result = chardet.detect(sample)
    encoding = result.get("encoding") or "utf-8"
    logger.debug("Detected encoding=%s confidence=%.2f", encoding, result.get("confidence", 0))
    return encoding


# =============================================================================
# Delimited helpers
# =============================================================================

def detect_delimiter(raw_bytes: bytes, encoding: str, sample_lines: int = 20) -> str:
    """
    Sniff the delimiter from the first N decoded lines.
    Falls back to comma when detection is inconclusive.
    """
    try:
        text  = raw_bytes[:65_536].decode(encoding, errors="replace")
        lines = text.splitlines()[:sample_lines]
        dialect = csv.Sniffer().sniff(
            "\n".join(lines),
            delimiters="".join(_DELIMITER_CANDIDATES),
        )
        logger.debug("Sniffed delimiter=%r", dialect.delimiter)
        return dialect.delimiter
    except csv.Error:
        logger.debug("Delimiter sniff failed — defaulting to comma")
        return ","


def _read_delimited(
    raw_bytes:  bytes,
    delimiter:  str | None,
    encoding:   str | None,
    has_header: bool,
    chunk_size: int | None,
) -> pd.DataFrame:
    enc = encoding or detect_encoding(raw_bytes)
    dlm = delimiter or detect_delimiter(raw_bytes, enc)
    buf = io.BytesIO(raw_bytes)

    header_arg = 0 if has_header else None
    common_kwargs = dict(
        sep             = dlm,
        encoding        = enc,
        dtype           = str,
        keep_default_na = False,
        on_bad_lines    = "warn",
        header          = header_arg,
    )

    if chunk_size:
        df = pd.concat(
            pd.read_csv(buf, chunksize=chunk_size, **common_kwargs),
            ignore_index=True,
        )
    else:
        df = pd.read_csv(buf, **common_kwargs)

    if not has_header:
        df.columns = [f"col_{i}" for i in range(len(df.columns))]

    # Strip BOM from first column name if present
    df.columns = [str(c).lstrip("\ufeff").strip() for c in df.columns]
    logger.info(
        "Read delimited: rows=%d cols=%d delimiter=%r encoding=%s",
        len(df), len(df.columns), dlm, enc,
    )
    return df


# =============================================================================
# Fixed-width helpers
# =============================================================================

def detect_fixed_width_columns(
    raw_bytes: bytes,
    encoding:  str,
    sample_lines: int = 50,
) -> "list[FixedWidthColumn]":
    """
    Heuristic auto-detection of fixed-width column boundaries.

    Strategy:
      1. Decode a sample of the file.
      2. Find columns of whitespace that are consistently blank across all
         sample data rows — these are likely field separators / boundaries.
      3. Return FixedWidthColumn objects for each detected field.

    NOTE: Auto-detection is best-effort. For production use, always supply
    explicit column specs via FileReference.columns.
    """
    # Import here to avoid circular at module load
    from app.models.schemas import FixedWidthColumn

    text  = raw_bytes[:131_072].decode(encoding, errors="replace")
    lines = [ln for ln in text.splitlines() if ln.strip()][:sample_lines]

    if not lines:
        raise ValueError("Cannot auto-detect fixed-width columns: file appears empty.")

    max_len = max(len(ln) for ln in lines)

    # Build a boolean mask: True = this position is blank in ALL sample rows
    blank_mask = []
    for pos in range(max_len):
        all_blank = all(pos >= len(ln) or ln[pos] == " " for ln in lines)
        blank_mask.append(all_blank)

    # Find transitions between blank and non-blank zones → column boundaries
    boundaries: list[tuple[int, int]] = []   # (start, end)
    in_field = False
    start    = 0

    for pos, is_blank in enumerate(blank_mask):
        if not is_blank and not in_field:
            start    = pos
            in_field = True
        elif is_blank and in_field:
            boundaries.append((start, pos))
            in_field = False

    if in_field:
        boundaries.append((start, max_len))

    if not boundaries:
        raise ValueError(
            "Fixed-width column auto-detection found no field boundaries. "
            "Please supply explicit column specs via FileReference.columns."
        )

    cols = [
        FixedWidthColumn(name=f"col_{i}", start=s, end=e)
        for i, (s, e) in enumerate(boundaries)
    ]
    logger.info("Auto-detected %d fixed-width columns", len(cols))
    return cols


def _parse_fixed_width_line(line: str, columns: "list[FixedWidthColumn]") -> dict:
    """Extract one row from a fixed-width line using column slice specs."""
    return {
        col.name: line[col.start : col.end]   # raw string; trim in normalise step
        for col in columns
    }


def _read_fixed_width(
    raw_bytes:        bytes,
    encoding:         str | None,
    columns:          "list[FixedWidthColumn] | None",
    skip_header_rows: int,
    skip_footer_rows: int,
    comment_char:     str | None,
    chunk_size:       int | None,
) -> pd.DataFrame:
    """
    Parse a fixed-width flat file into a DataFrame.

    Handles:
      - Arbitrary column positions (non-contiguous, overlapping allowed)
      - Header / footer row skipping
      - Comment-line filtering
      - Chunked processing for large files
    """
    enc  = encoding or detect_encoding(raw_bytes)
    text = raw_bytes.decode(enc, errors="replace")
    all_lines = text.splitlines()

    # Strip footer first (before header so indices are stable)
    if skip_footer_rows > 0:
        all_lines = all_lines[: len(all_lines) - skip_footer_rows]

    # Strip header rows
    data_lines = all_lines[skip_header_rows:]

    # Drop comment lines
    if comment_char:
        data_lines = [ln for ln in data_lines if not ln.startswith(comment_char)]

    # Drop completely empty lines
    data_lines = [ln for ln in data_lines if ln.strip()]

    # Auto-detect columns if not provided
    if not columns:
        sample_bytes = "\n".join(data_lines[:50]).encode(enc)
        columns = detect_fixed_width_columns(sample_bytes, enc)
        logger.warning(
            "Fixed-width columns were not provided; auto-detected %d columns. "
            "For reliable results supply explicit column specs.",
            len(columns),
        )

    # Parse in chunks to keep memory bounded
    size  = chunk_size or len(data_lines)
    dfs: list[pd.DataFrame] = []

    for offset in range(0, len(data_lines), size):
        batch   = data_lines[offset : offset + size]
        records = [_parse_fixed_width_line(ln, columns) for ln in batch]
        dfs.append(pd.DataFrame(records))

    df = pd.concat(dfs, ignore_index=True) if dfs else pd.DataFrame(columns=[c.name for c in columns])

    logger.info(
        "Read fixed-width: rows=%d cols=%d encoding=%s skipped_header=%d skipped_footer=%d",
        len(df), len(df.columns), enc, skip_header_rows, skip_footer_rows,
    )
    return df


# =============================================================================
# Public unified reader
# =============================================================================

def read_dataframe(
    raw_bytes: bytes,
    file_ref:  "FileReference | None" = None,
    chunk_size: int | None = None,
    # Legacy keyword arguments (delimited-only callers)
    delimiter:  str | None = None,
    encoding:   str | None = None,
) -> pd.DataFrame:
    """
    Unified entry point.  Dispatches to the correct reader based on
    file_ref.file_format (defaulting to DELIMITED for backward compat).

    Parameters
    ----------
    raw_bytes  : raw file bytes from Azure Blob
    file_ref   : FileReference Pydantic model (carries all format options)
    chunk_size : rows per processing chunk for large files
    delimiter  : legacy override (used when file_ref is None)
    encoding   : legacy override (used when file_ref is None)
    """
    from app.models.schemas import FileFormat

    # ── Resolve options from file_ref or legacy kwargs ────────────────────────
    if file_ref is None:
        # Backward-compatible: treat as delimited
        return _read_delimited(
            raw_bytes  = raw_bytes,
            delimiter  = delimiter,
            encoding   = encoding,
            has_header = True,
            chunk_size = chunk_size,
        )

    fmt = file_ref.file_format

    if fmt == FileFormat.FIXED_WIDTH:
        return _read_fixed_width(
            raw_bytes        = raw_bytes,
            encoding         = file_ref.encoding,
            columns          = file_ref.columns,
            skip_header_rows = file_ref.skip_header_rows,
            skip_footer_rows = file_ref.skip_footer_rows,
            comment_char     = file_ref.comment_char,
            chunk_size       = chunk_size,
        )

    # Default → DELIMITED
    return _read_delimited(
        raw_bytes  = raw_bytes,
        delimiter  = file_ref.delimiter,
        encoding   = file_ref.encoding,
        has_header = file_ref.has_header,
        chunk_size = chunk_size,
    )


# =============================================================================
# Normalisation (shared by both formats)
# =============================================================================

def normalise_dataframe(
    df: pd.DataFrame,
    trim_whitespace: bool = True,
    case_sensitive:  bool = True,
    ignore_columns:  "list[str] | None" = None,
) -> pd.DataFrame:
    """Apply normalisation rules before comparison (format-agnostic)."""
    df = df.copy()

    if ignore_columns:
        drop = [c for c in ignore_columns if c in df.columns]
        df.drop(columns=drop, inplace=True)

    if trim_whitespace:
        df = df.applymap(lambda x: x.strip() if isinstance(x, str) else x)

    if not case_sensitive:
        df = df.applymap(lambda x: x.upper() if isinstance(x, str) else x)

    return df
