#!/usr/bin/env bash
# Scale test: 50M transactions -> separate DuckDB warehouse -> Parquet -> PySpark vs DuckDB benchmark.
# Needs about 3 GB free disk and 8 GB RAM. Takes about 15-20 minutes on a laptop (8 cores, 8 GB).
set -euo pipefail
cd "$(dirname "$0")/.."
ROWS="${ROWS:-50000000}"
OUT="data/raw_50m"
PY=".venv/bin/python"

if [ ! -f "$OUT/_manifest.json" ]; then
  "$PY" -m generator.generate --rows "$ROWS" --out "$OUT"
fi
start=$(date +%s)
( cd dbt && RAW_DATA_PATH="../$OUT" DUCKDB_PATH="../warehouse/payments_50m.duckdb" \
    ../.venv/bin/dbt build --profiles-dir . --full-refresh --target-path target_50m )
echo "dbt build (50M) took $(( $(date +%s) - start ))s" | tee spark/results/dbt_build_50m_seconds.txt
"$PY" scripts/export_marts.py --db warehouse/payments_50m.duckdb --out data/exports_50m --partitioned-fact
"$PY" spark/reconcile.py --label 50m --db warehouse/payments_50m.duckdb --exports data/exports_50m
