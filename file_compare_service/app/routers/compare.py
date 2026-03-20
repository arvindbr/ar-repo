"""
app/routers/compare.py
All /compare endpoints.

POST /compare              → submit async job
GET  /compare/{job_id}     → poll result / full JSON diff
GET  /compare/{job_id}/export/csv    → download CSV
GET  /compare/{job_id}/export/excel  → download Excel
GET  /compare/{job_id}/summary       → AI narrative only
"""
from __future__ import annotations

import asyncio
import logging
import uuid
from datetime import datetime, timezone
from typing import Any

from fastapi import APIRouter, BackgroundTasks, HTTPException
from fastapi.responses import Response

from app.config import get_settings
from app.models.schemas import (
    CompareRequest, CompareResponse, CompareResult,
    DiffRow, DiffStats, JobStatus,
)
from app.services.ai_service      import generate_summary
from app.services.azure_service   import download_blob
from app.services.diff_service    import compare_dataframes
from app.services.export_service  import export_csv, export_excel
from app.utils.file_utils         import read_dataframe

router   = APIRouter(prefix="/compare", tags=["compare"])
logger   = logging.getLogger(__name__)
settings = get_settings()

# ── In-memory job store (swap for Redis in production) ────────────────────────
# { job_id: CompareResult }
_jobs: dict[str, CompareResult] = {}


# ── Background task ───────────────────────────────────────────────────────────

async def _run_comparison(job_id: str, req: CompareRequest) -> None:
    job = _jobs[job_id]
    job.status = JobStatus.RUNNING
    t_start = datetime.now(timezone.utc)

    try:
        logger.info("[%s] Downloading file A: %s/%s", job_id, req.file_a.container, req.file_a.blob_path)
        bytes_a, bytes_b = await asyncio.gather(
            download_blob(req.file_a),
            download_blob(req.file_b),
        )

        logger.info("[%s] Parsing files (format_a=%s format_b=%s)",
                    job_id, req.file_a.file_format, req.file_b.file_format)
        df_a = read_dataframe(
            bytes_a,
            file_ref   = req.file_a,
            chunk_size = settings.chunk_size_rows,
        )
        df_b = read_dataframe(
            bytes_b,
            file_ref   = req.file_b,
            chunk_size = settings.chunk_size_rows,
        )

        logger.info("[%s] Running diff", job_id)
        stats, all_rows = compare_dataframes(
            df_a            = df_a,
            df_b            = df_b,
            key_columns     = req.key_columns,
            ignore_columns  = req.ignore_columns,
            case_sensitive  = req.case_sensitive,
            trim_whitespace = req.trim_whitespace,
            include_matched = req.include_matched,
        )

        # Store full row list for export; cap preview for JSON response
        job.diff_rows       = all_rows[:settings.max_preview_rows]
        job.total_diff_rows = len(all_rows)
        job.stats           = stats
        # Keep full rows in a side-car attribute for export endpoints
        job._all_rows = all_rows  # type: ignore[attr-defined]

        # AI summary
        if req.generate_summary:
            logger.info("[%s] Generating AI summary", job_id)
            job.ai_summary = await generate_summary(
                stats,
                req.file_a.blob_path,
                req.file_b.blob_path,
            )

        t_end = datetime.now(timezone.utc)
        job.status       = JobStatus.COMPLETE
        job.completed_at = t_end.isoformat()
        job.duration_ms  = int((t_end - t_start).total_seconds() * 1000)
        logger.info("[%s] Complete in %d ms", job_id, job.duration_ms)

    except Exception as exc:
        logger.exception("[%s] Comparison failed: %s", job_id, exc)
        job.status = JobStatus.FAILED
        job.error  = str(exc)


# ── Endpoints ─────────────────────────────────────────────────────────────────

@router.post("", response_model=CompareResponse, status_code=202)
async def submit_compare(req: CompareRequest, background_tasks: BackgroundTasks):
    """
    Submit a file comparison job.
    Returns a job_id immediately; the comparison runs asynchronously.
    Poll GET /compare/{job_id} to retrieve results.
    """
    job_id = str(uuid.uuid4())
    _jobs[job_id] = CompareResult(
        job_id     = job_id,
        status     = JobStatus.PENDING,
        request    = req,
        created_at = datetime.now(timezone.utc).isoformat(),
    )
    background_tasks.add_task(_run_comparison, job_id, req)
    logger.info("Job submitted job_id=%s", job_id)
    return CompareResponse(
        job_id  = job_id,
        status  = JobStatus.PENDING,
        message = f"Job accepted. Poll GET /compare/{job_id} for results.",
    )


@router.get("/{job_id}", response_model=CompareResult)
async def get_result(job_id: str):
    """
    Poll the comparison result.
    Returns full JSON diff (diff_rows capped at {max_preview_rows} rows).
    When status=complete, use /export/csv or /export/excel for full data.
    """
    job = _jobs.get(job_id)
    if not job:
        raise HTTPException(status_code=404, detail=f"Job {job_id!r} not found.")
    return job


@router.get("/{job_id}/export/csv")
async def export_csv_endpoint(job_id: str):
    """Download the complete diff as a CSV file."""
    job = _resolve_complete_job(job_id)
    all_rows: list[DiffRow] = getattr(job, "_all_rows", job.diff_rows or [])
    csv_bytes = export_csv(all_rows)
    return Response(
        content     = csv_bytes,
        media_type  = "text/csv",
        headers     = {"Content-Disposition": f'attachment; filename="diff_{job_id}.csv"'},
    )


@router.get("/{job_id}/export/excel")
async def export_excel_endpoint(job_id: str):
    """Download the complete diff as a multi-sheet Excel workbook."""
    job = _resolve_complete_job(job_id)
    all_rows: list[DiffRow] = getattr(job, "_all_rows", job.diff_rows or [])
    xlsx_bytes = export_excel(all_rows, job.stats, job.ai_summary)
    return Response(
        content    = xlsx_bytes,
        media_type = "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        headers    = {"Content-Disposition": f'attachment; filename="diff_{job_id}.xlsx"'},
    )


@router.get("/{job_id}/summary")
async def get_summary(job_id: str):
    """Return only the AI narrative summary for a completed job."""
    job = _resolve_complete_job(job_id)
    return {"job_id": job_id, "ai_summary": job.ai_summary}


# ── helpers ───────────────────────────────────────────────────────────────────

def _resolve_complete_job(job_id: str) -> CompareResult:
    job = _jobs.get(job_id)
    if not job:
        raise HTTPException(status_code=404, detail=f"Job {job_id!r} not found.")
    if job.status == JobStatus.RUNNING or job.status == JobStatus.PENDING:
        raise HTTPException(status_code=202, detail="Job still processing. Try again shortly.")
    if job.status == JobStatus.FAILED:
        raise HTTPException(status_code=500, detail=f"Job failed: {job.error}")
    return job
