#!/usr/bin/env bash
# ============================================================================
# Bootstrap the Snowflake Starter Kit directory layout.
#
# Usage:
#   ./scripts/bootstrap_directories.sh [target_dir]
#
# If target_dir is omitted, creates the layout in the current directory under
# a folder named 'snowflake-starter-kit'.
#
# Idempotent: safe to re-run. Will not overwrite existing files.
# ============================================================================

set -euo pipefail

TARGET="${1:-snowflake-starter-kit}"

echo "Creating directory layout under: $TARGET"

mkdir -p "$TARGET"/{.claude/commands,.github/{prompts,chatmodes,instructions,workflows},.vscode}

# AI assistance
mkdir -p "$TARGET"/agents/{etl-pipeline-builder,query-optimizer,schema-migrator,data-quality-guardian,test-data-factory,docs-writer}
mkdir -p "$TARGET"/skills/{snowflake-sql-author,snowflake-performance-tuner,snowflake-security-auditor,snowflake-cost-optimizer,snowflake-data-modeler,snowflake-notebook-author}

# Boilerplates
mkdir -p "$TARGET"/boilerplates/dbt/{macros,models/{staging,intermediate,marts},seeds,snapshots,tests}
mkdir -p "$TARGET"/boilerplates/streamlit/pages
mkdir -p "$TARGET"/boilerplates/airflow/dags
mkdir -p "$TARGET"/boilerplates/snowpark-app/{deploy,src/{lib,procedures,udfs},tests}
mkdir -p "$TARGET"/boilerplates/data-quality/checks
mkdir -p "$TARGET"/boilerplates/cicd

# Vibe-coding workflows
mkdir -p "$TARGET"/workflows/frongello-attribution/{spec,prompts,reference,implementation,tests}

# Templates
mkdir -p "$TARGET"/templates/{sql,python,yaml}

# Project code
mkdir -p "$TARGET"/sql/{ddl,dml,queries,procedures,migrations}
mkdir -p "$TARGET"/python/{connectors,etl,utils}
mkdir -p "$TARGET"/{notebooks,tests,scripts,config}
mkdir -p "$TARGET"/docs/{adr,models,onboarding}

# Verify
DIR_COUNT=$(find "$TARGET" -type d | wc -l | tr -d ' ')
echo ""
echo "✅ Created $DIR_COUNT directories."
echo ""

if [[ "$DIR_COUNT" -lt 70 ]]; then
    echo "⚠️  Expected ~76 directories. Got $DIR_COUNT."
    echo "    If you ran this under POSIX sh or dash, brace expansion may have failed."
    echo "    Re-run with: bash $0 $TARGET"
    exit 1
fi

echo "Next steps:"
echo "  1. cd $TARGET"
echo "  2. Drop your files into the appropriate directories"
echo "  3. Or unzip the starter kit ZIP over this layout to populate it"
