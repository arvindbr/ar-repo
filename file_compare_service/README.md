# File Compare Service

Automated REST API to compare any two files from Azure Blob Storage.
Supports **delimited** (CSV / TSV / pipe / semicolon) and **fixed-width** (positional / mainframe) files — including mixed-format comparisons.
Returns a JSON diff report, column-level change breakdown, CSV/Excel export, and an AI narrative summary.

## Project Structure

```
file_compare_service/
├── app/
│   ├── main.py                  # FastAPI app entry point
│   ├── config.py                # Settings (env vars)
│   ├── routers/
│   │   └── compare.py           # /compare endpoints
│   ├── services/
│   │   ├── azure_service.py     # Azure Blob download
│   │   ├── diff_service.py      # Core comparison logic
│   │   ├── export_service.py    # CSV / Excel export
│   │   └── ai_service.py        # OpenAI narrative summary
│   ├── models/
│   │   └── schemas.py           # Pydantic models (FileFormat, FixedWidthColumn, …)
│   └── utils/
│       └── file_utils.py        # Unified reader: delimited + fixed-width
├── tests/
│   └── test_compare.py          # 22 unit tests
├── scripts/
│   └── sample_request.sh        # curl examples (delimited, fixed-width, mixed)
├── requirements.txt
├── Dockerfile
├── docker-compose.yml
└── .env.example
```

## Quick Start

```bash
cp .env.example .env          # fill in Azure + OpenAI credentials
pip install -r requirements.txt
uvicorn app.main:app --reload  # → http://localhost:8000/docs
```

## API Endpoints

| Method | Path | Description |
|--------|------|-------------|
| POST | `/compare` | Submit a comparison job (async) |
| GET  | `/compare/{job_id}` | Poll job status / fetch JSON diff |
| GET  | `/compare/{job_id}/export/csv` | Download full diff as CSV |
| GET  | `/compare/{job_id}/export/excel` | Download diff as multi-sheet Excel |
| GET  | `/compare/{job_id}/summary` | AI narrative summary only |
| GET  | `/health` | Health check |

## File Format Support

### Delimited (`file_format: "delimited"`)
Auto-detects delimiter (`,` `\t` `|` `;`) and encoding. Override with explicit values.

```json
{
  "container":   "my-container",
  "blob_path":   "data/prices.csv",
  "file_format": "delimited",
  "delimiter":   null,
  "has_header":  true,
  "encoding":    null
}
```

### Fixed-Width (`file_format: "fixed_width"`)
Provide explicit column specs with 0-based `start`/`end` positions (Python slice semantics: `line[start:end]`).

```json
{
  "container":        "my-container",
  "blob_path":        "data/prices.dat",
  "file_format":      "fixed_width",
  "skip_header_rows": 2,
  "skip_footer_rows": 1,
  "comment_char":     "*",
  "columns": [
    {"name": "cusip",  "start": 0,  "end": 10},
    {"name": "ccy",    "start": 10, "end": 13},
    {"name": "price",  "start": 13, "end": 23},
    {"name": "status", "start": 23, "end": 30}
  ]
}
```

**Mixed-format** comparisons are fully supported — file A can be delimited while file B is fixed-width.

