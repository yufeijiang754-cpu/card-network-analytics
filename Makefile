# Card Payment Network Analytics & Data Quality Platform (all data synthetic)
PY  := .venv/bin/python
DBT := ../.venv/bin/dbt
ROWS ?= 2000000

.PHONY: help all setup data build dq analysis spark spark-50m docs dashboard test clean

help:           ## list targets
	@grep -E '^[a-z0-9-]+:.*## ' Makefile | sed -E 's/:.*## /\t/'

all:            ## full pipeline (same as ./run_all.sh)
	./run_all.sh

setup:          ## create venv + install pinned dependencies
	test -x $(PY) || python3 -m venv .venv
	$(PY) -m pip install -q -r requirements.txt

data:           ## generate synthetic data (ROWS=...)
	$(PY) -m scripts.export_seeds
	$(PY) -m generator.generate --rows $(ROWS)

build:          ## dbt seeds + models + tests (full refresh)
	cd dbt && $(DBT) build --profiles-dir . --full-refresh

dq: build       ## DQ results + detection report vs answer key
	$(PY) dq/compare_answer_key.py

analysis:       ## run analysis/*.sql -> analysis/results/*.csv
	$(PY) scripts/run_analysis.py

spark:          ## export marts and reconcile PySpark vs DuckDB (2M)
	$(PY) scripts/export_marts.py --partitioned-fact
	$(PY) spark/reconcile.py --label 2m

spark-50m:      ## 50M-row scale test (about 15-20 min)
	./scripts/run_50m.sh

docs:           ## dbt docs site with lineage graph
	cd dbt && $(DBT) docs generate --profiles-dir . && $(DBT) docs serve --profiles-dir . --port 8080

dashboard:      ## Streamlit dashboard on :8501
	.venv/bin/streamlit run dashboard/app.py

test:           ## pytest suite
	$(PY) -m pytest -q -p no:warnings

clean:          ## remove generated data, warehouse and build artifacts
	rm -rf data/raw data/raw_50m data/exports data/exports_50m data/dq_answer_key.csv warehouse/*.duckdb \
	       dbt/target dbt/target_50m dbt/logs spark/output
