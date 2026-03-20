#!/usr/bin/env bash
# =============================================================================
# scripts/sample_request.sh
# Example curl calls for the File Compare Service
# Covers: delimited files, fixed-width files, mixed format comparison
# =============================================================================

BASE_URL="http://localhost:8000"

echo ""
echo "──────────────────────────────────────────────────"
echo " 1. Health check"
echo "──────────────────────────────────────────────────"
curl -s "$BASE_URL/health" | python3 -m json.tool


echo ""
echo "──────────────────────────────────────────────────"
echo " 2a. Submit — DELIMITED comparison (key-based + AI summary)"
echo "──────────────────────────────────────────────────"
JOB=$(curl -s -X POST "$BASE_URL/compare" \
  -H "Content-Type: application/json" \
  -d '{
    "file_a": {
      "container":   "my-container",
      "blob_path":   "data/prices_2026_03_01.csv",
      "file_format": "delimited",
      "delimiter":   null,
      "has_header":  true
    },
    "file_b": {
      "container":   "my-container",
      "blob_path":   "data/prices_2026_03_11.csv",
      "file_format": "delimited",
      "delimiter":   null,
      "has_header":  true
    },
    "key_columns":      ["cusip", "ccy"],
    "ignore_columns":   ["load_ts", "updated_by"],
    "case_sensitive":   false,
    "trim_whitespace":  true,
    "include_matched":  false,
    "generate_summary": true
  }')
echo "$JOB" | python3 -m json.tool
JOB_ID_CSV=$(echo "$JOB" | python3 -c "import sys,json; print(json.load(sys.stdin)['job_id'])")
echo "Job ID (delimited): $JOB_ID_CSV"


echo ""
echo "──────────────────────────────────────────────────"
echo " 2b. Submit — FIXED-WIDTH comparison"
echo "──────────────────────────────────────────────────"
# Column specs: name, 0-based start, end (exclusive = Python slice)
#   CUSIP   : chars 0-10
#   CCY     : chars 10-13
#   PRICE   : chars 13-23
#   STATUS  : chars 23-30
JOB_FW=$(curl -s -X POST "$BASE_URL/compare" \
  -H "Content-Type: application/json" \
  -d '{
    "file_a": {
      "container":        "my-container",
      "blob_path":        "data/prices_2026_03_01.dat",
      "file_format":      "fixed_width",
      "encoding":         "utf-8",
      "skip_header_rows": 2,
      "skip_footer_rows": 1,
      "comment_char":     "*",
      "columns": [
        {"name": "cusip",  "start": 0,  "end": 10, "dtype": "str"},
        {"name": "ccy",    "start": 10, "end": 13, "dtype": "str"},
        {"name": "price",  "start": 13, "end": 23, "dtype": "float"},
        {"name": "status", "start": 23, "end": 30, "dtype": "str"}
      ]
    },
    "file_b": {
      "container":        "my-container",
      "blob_path":        "data/prices_2026_03_11.dat",
      "file_format":      "fixed_width",
      "encoding":         "utf-8",
      "skip_header_rows": 2,
      "skip_footer_rows": 1,
      "comment_char":     "*",
      "columns": [
        {"name": "cusip",  "start": 0,  "end": 10, "dtype": "str"},
        {"name": "ccy",    "start": 10, "end": 13, "dtype": "str"},
        {"name": "price",  "start": 13, "end": 23, "dtype": "float"},
        {"name": "status", "start": 23, "end": 30, "dtype": "str"}
      ]
    },
    "key_columns":      ["cusip", "ccy"],
    "ignore_columns":   null,
    "case_sensitive":   false,
    "trim_whitespace":  true,
    "include_matched":  false,
    "generate_summary": true
  }')
echo "$JOB_FW" | python3 -m json.tool
JOB_ID_FW=$(echo "$JOB_FW" | python3 -c "import sys,json; print(json.load(sys.stdin)['job_id'])")
echo "Job ID (fixed-width): $JOB_ID_FW"


echo ""
echo "──────────────────────────────────────────────────"
echo " 2c. Submit — MIXED FORMAT (CSV vs fixed-width)"
echo "──────────────────────────────────────────────────"
curl -s -X POST "$BASE_URL/compare" \
  -H "Content-Type: application/json" \
  -d '{
    "file_a": {
      "container":   "my-container",
      "blob_path":   "data/source.csv",
      "file_format": "delimited"
    },
    "file_b": {
      "container":        "my-container",
      "blob_path":        "data/target.dat",
      "file_format":      "fixed_width",
      "skip_header_rows": 1,
      "columns": [
        {"name": "cusip",  "start": 0,  "end": 10},
        {"name": "ccy",    "start": 10, "end": 13},
        {"name": "price",  "start": 13, "end": 23},
        {"name": "status", "start": 23, "end": 30}
      ]
    },
    "key_columns":      ["cusip"],
    "generate_summary": true
  }' | python3 -m json.tool


echo ""
echo "──────────────────────────────────────────────────"
echo " 3. Poll result (retry until complete)"
echo "──────────────────────────────────────────────────"
JOB_ID="$JOB_ID_FW"   # change to whichever job you want to poll
for i in {1..20}; do
  STATUS=$(curl -s "$BASE_URL/compare/$JOB_ID" | python3 -c "import sys,json; print(json.load(sys.stdin)['status'])")
  echo "  Attempt $i: status=$STATUS"
  if [[ "$STATUS" == "complete" || "$STATUS" == "failed" ]]; then break; fi
  sleep 3
done

echo ""
echo "Full result:"
curl -s "$BASE_URL/compare/$JOB_ID" | python3 -m json.tool


echo ""
echo "──────────────────────────────────────────────────"
echo " 4. AI summary only"
echo "──────────────────────────────────────────────────"
curl -s "$BASE_URL/compare/$JOB_ID/summary" | python3 -m json.tool


echo ""
echo "──────────────────────────────────────────────────"
echo " 5. Download CSV diff"
echo "──────────────────────────────────────────────────"
curl -s -o "diff_${JOB_ID}.csv" "$BASE_URL/compare/$JOB_ID/export/csv"
echo "Saved: diff_${JOB_ID}.csv"


echo ""
echo "──────────────────────────────────────────────────"
echo " 6. Download Excel diff"
echo "──────────────────────────────────────────────────"
curl -s -o "diff_${JOB_ID}.xlsx" "$BASE_URL/compare/$JOB_ID/export/excel"
echo "Saved: diff_${JOB_ID}.xlsx"
