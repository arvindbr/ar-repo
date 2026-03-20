"""
app/models/schemas.py
Request and response models for the File Compare Service.
Supports both delimited (CSV/TSV/pipe) and fixed-width files.
"""
from __future__ import annotations

from enum import Enum
from typing import Any

from pydantic import BaseModel, Field, model_validator


# ── Enums ─────────────────────────────────────────────────────────────────────

class JobStatus(str, Enum):
    PENDING    = "pending"
    RUNNING    = "running"
    COMPLETE   = "complete"
    FAILED     = "failed"


class DiffType(str, Enum):
    ONLY_IN_A  = "only_in_a"    # row exists in file A, missing from B
    ONLY_IN_B  = "only_in_b"    # row exists in file B, missing from A
    MODIFIED   = "modified"     # row matched by key but values changed
    MATCHED    = "matched"      # identical in both files


class FileFormat(str, Enum):
    DELIMITED   = "delimited"    # CSV, TSV, pipe-separated, etc. (auto-detected)
    FIXED_WIDTH = "fixed_width"  # positional / mainframe-style flat files


# ── Fixed-width column spec ───────────────────────────────────────────────────

class FixedWidthColumn(BaseModel):
    """
    Definition of one column in a fixed-width file.
    start and end are 0-based, end-exclusive (Python slice semantics):
        line[start:end]
    """
    name:   str = Field(...,  description="Column name")
    start:  int = Field(...,  ge=0, description="Start position (0-based, inclusive)")
    end:    int = Field(...,  ge=1, description="End position (0-based, exclusive)")
    dtype:  str = Field("str", description="Expected data type hint: str | int | float | date")

    @model_validator(mode="after")
    def end_after_start(self) -> "FixedWidthColumn":
        if self.end <= self.start:
            raise ValueError(f"Column '{self.name}': end ({self.end}) must be > start ({self.start})")
        return self


# ── Request ───────────────────────────────────────────────────────────────────

class FileReference(BaseModel):
    container:    str        = Field(...,  description="Azure Blob container name")
    blob_path:    str        = Field(...,  description="Full blob path, e.g. data/prices/file_a.csv")

    # ── Format selection ──────────────────────────────────────────────────────
    file_format:  FileFormat = Field(
        FileFormat.DELIMITED,
        description="'delimited' for CSV/TSV/pipe files (auto-detected); "
                    "'fixed_width' for positional flat files."
    )

    # ── Delimited options (ignored for fixed_width) ───────────────────────────
    delimiter:    str | None = Field(
        None,
        description="[delimited only] Column delimiter. Auto-detected if omitted."
    )
    encoding:     str | None = Field(
        None,
        description="File encoding. Auto-detected if omitted (utf-8, latin-1, etc.)"
    )
    has_header:   bool       = Field(
        True,
        description="[delimited only] Whether the first row is a header. "
                    "If False, columns are named col_0, col_1, …"
    )

    # ── Fixed-width options (required when file_format = fixed_width) ─────────
    columns:      list[FixedWidthColumn] | None = Field(
        None,
        description="[fixed_width only] Ordered list of column definitions "
                    "(name, start, end). Required when file_format=fixed_width."
    )
    skip_header_rows: int = Field(
        0,
        ge=0,
        description="[fixed_width only] Number of header/title rows to skip before data begins."
    )
    skip_footer_rows: int = Field(
        0,
        ge=0,
        description="[fixed_width only] Number of trailer/footer rows to skip at end of file."
    )
    comment_char: str | None = Field(
        None,
        description="[fixed_width only] Lines starting with this character are skipped (e.g. '#', '*')."
    )

    @model_validator(mode="after")
    def validate_fixed_width(self) -> "FileReference":
        if self.file_format == FileFormat.FIXED_WIDTH:
            if not self.columns:
                raise ValueError(
                    "columns is required when file_format='fixed_width'. "
                    "Provide a list of FixedWidthColumn definitions."
                )
        return self


class CompareRequest(BaseModel):
    file_a:         FileReference
    file_b:         FileReference
    key_columns:    list[str] | None = Field(
        None,
        description="Column name(s) to use as the join key for modified-row detection. "
                    "If omitted, comparison is positional (row-by-row)."
    )
    ignore_columns: list[str] | None = Field(
        None,
        description="Column names to exclude from comparison (e.g. audit timestamps)."
    )
    case_sensitive: bool = Field(True,  description="Whether string comparisons are case-sensitive.")
    trim_whitespace: bool = Field(True,  description="Trim leading/trailing whitespace before comparing.")
    include_matched: bool = Field(False, description="Include unchanged rows in the diff output.")
    generate_summary: bool = Field(True, description="Generate an AI narrative summary via OpenAI.")

    @model_validator(mode="after")
    def validate_keys(self) -> "CompareRequest":
        if self.key_columns and len(self.key_columns) == 0:
            raise ValueError("key_columns must contain at least one column name if provided.")
        return self


# ── Column diff detail ────────────────────────────────────────────────────────

class ColumnChange(BaseModel):
    column:     str
    value_a:    Any
    value_b:    Any


class DiffRow(BaseModel):
    row_index_a:    int | None = None
    row_index_b:    int | None = None
    diff_type:      DiffType
    key_values:     dict[str, Any] | None = None
    changes:        list[ColumnChange] | None = None   # populated for MODIFIED rows
    row_a:          dict[str, Any] | None = None
    row_b:          dict[str, Any] | None = None


# ── Stats ─────────────────────────────────────────────────────────────────────

class ColumnStats(BaseModel):
    column:         str
    change_count:   int
    change_pct:     float


class DiffStats(BaseModel):
    total_rows_a:       int
    total_rows_b:       int
    rows_only_in_a:     int
    rows_only_in_b:     int
    rows_matched:       int
    rows_modified:      int
    pct_unchanged:      float
    pct_removed:        float
    pct_added:          float
    pct_modified:       float
    columns_in_a:       list[str]
    columns_in_b:       list[str]
    columns_added:      list[str]   # in B not in A
    columns_removed:    list[str]   # in A not in B
    column_change_counts: list[ColumnStats]


# ── Response ──────────────────────────────────────────────────────────────────

class CompareResponse(BaseModel):
    job_id:         str
    status:         JobStatus
    message:        str | None = None


class CompareResult(BaseModel):
    job_id:         str
    status:         JobStatus
    request:        CompareRequest
    stats:          DiffStats | None = None
    diff_rows:      list[DiffRow] | None = None   # capped at MAX_PREVIEW_ROWS
    total_diff_rows: int | None = None
    ai_summary:     str | None = None
    error:          str | None = None
    created_at:     str | None = None
    completed_at:   str | None = None
    duration_ms:    int | None = None


class HealthResponse(BaseModel):
    status:  str = "ok"
    version: str = "1.0.0"
    env:     str
