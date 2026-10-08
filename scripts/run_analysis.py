"""Run every analysis/*.sql file against the DuckDB warehouse and save results as CSV.

A file may contain several statements separated by ';'. Each result is written to
analysis/results/<file>[_partN].csv. A short preview is printed.
"""

from __future__ import annotations

import argparse
import re
import time
from pathlib import Path

import duckdb

ROOT = Path(__file__).resolve().parents[1]


def statements(sql: str) -> list[str]:
    sql = re.sub(r"--[^\n]*", "", sql)  # comments may contain ';'
    return [s.strip() for s in sql.split(";") if s.strip()]


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--db", default=str(ROOT / "warehouse/payments.duckdb"))
    ap.add_argument("--quiet", action="store_true")
    a = ap.parse_args()
    out = ROOT / "analysis/results"
    out.mkdir(parents=True, exist_ok=True)
    con = duckdb.connect(a.db, read_only=True)
    for f in sorted((ROOT / "analysis").glob("*.sql")):
        stmts = statements(f.read_text())
        for i, s in enumerate(stmts, start=1):
            t0 = time.time()
            df = con.sql(s).df()
            name = f.stem if len(stmts) == 1 else f"{f.stem}_part{chr(64 + i)}"
            df.to_csv(out / f"{name}.csv", index=False)
            print(f"{name:<45} {len(df):>6} rows  {time.time() - t0:5.2f}s")
            if not a.quiet:
                print(df.head(8).to_string(index=False), "\n")


if __name__ == "__main__":
    main()
