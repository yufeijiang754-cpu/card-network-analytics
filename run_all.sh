#!/usr/bin/env bash
# =============================================================================
# One-command end-to-end run of the Card Payment Network Analytics platform.
#   ./run_all.sh               # 2M transactions (about 5-8 min after dependencies are installed)
#   ROWS=500000 ./run_all.sh   # smaller / faster
#   SKIP_SPARK=1 ./run_all.sh  # skip PySpark reconciliation (no Java)
# Requirements: Python 3.10+ (tested on 3.11); Java 11/17 for PySpark.
# All data is SYNTHETIC.
# =============================================================================
set -euo pipefail
cd "$(dirname "$0")"

ROWS="${ROWS:-2000000}"
PYTHON_BIN="${PYTHON_BIN:-python3}"
PY=".venv/bin/python"
DBT="../.venv/bin/dbt"
step() { printf '\n\033[1;34m==> %s\033[0m\n' "$*"; }
t0=$(date +%s)

step "1/8  Python environment"
if [ ! -x "$PY" ]; then "$PYTHON_BIN" -m venv .venv; fi
"$PY" -m pip install -q --upgrade pip
"$PY" -m pip install -q -r requirements.txt

step "2/8  Synthetic data (${ROWS} transactions) + reference seeds"
"$PY" -m scripts.export_seeds
"$PY" -m generator.generate --rows "$ROWS"

step "3/8  dbt: seeds, models, tests (full refresh)"
mkdir -p warehouse
( cd dbt && "$DBT" build --profiles-dir . --full-refresh )

step "4/8  dbt docs, lineage export and documentation coverage"
( cd dbt && "$DBT" docs generate --profiles-dir . > /dev/null )
"$PY" scripts/export_lineage.py
"$PY" scripts/check_doc_coverage.py

step "5/8  Data-quality detection report vs. answer key"
"$PY" dq/compare_answer_key.py

step "6/8  Business analysis SQL"
"$PY" scripts/run_analysis.py --quiet

step "7/8  Exports + PySpark reconciliation"
"$PY" scripts/export_marts.py --partitioned-fact > /dev/null
if [ "${SKIP_SPARK:-0}" = "1" ] || ! command -v java > /dev/null 2>&1; then
  echo "Skipping PySpark (SKIP_SPARK=1 or Java not found)."
else
  label=$([ "$ROWS" = "2000000" ] && echo "2m" || echo "${ROWS}")
  "$PY" spark/reconcile.py --label "$label"
fi

step "8/8  Test suite"
if [ "${SKIP_SPARK:-0}" = "1" ] || ! command -v java > /dev/null 2>&1; then
  "$PY" -m pytest -q -p no:warnings --ignore=tests/test_spark_jobs.py
else
  "$PY" -m pytest -q -p no:warnings
fi

printf '\n\033[1;32mDone in %ss.\033[0m\n' "$(( $(date +%s) - t0 ))"
cat <<'MSG'
Next steps:
  make dashboard        # Streamlit on http://localhost:8501
  make docs             # dbt docs + lineage on http://localhost:8080
  open dq/reports/detection_report.md docs/INSIGHTS.md
MSG
