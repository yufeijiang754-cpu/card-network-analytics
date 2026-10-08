"""Score the dbt data-quality tests against the generator's answer key.

Reads the latest `dbt test` / `dbt build` artifacts (manifest.json, run_results.json) and the
failing rows stored by `store_failures` in the dq_audit schema, then compares the flagged record
keys with data/dq_answer_key.csv to produce:

  * recall per injected issue type / column  (did we catch what was injected?)
  * precision per test                        (is everything we flagged really a defect?)
  * an automatic explanation for every miss
  * a grace-window sensitivity table for the timeliness check
  * expectation checks: raw tests WARN where defects were injected, trusted-layer tests PASS

Outputs: dq/reports/detection_report.md, dq/reports/detection_by_issue.csv and the
dq.dq_detection_scorecard table (used by the Streamlit Data Quality Monitor).
Exit code 1 if any expectation fails.
"""

from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime
from pathlib import Path

import duckdb
import pandas as pd

ROOT = Path(__file__).resolve().parents[1]

# test macro -> issue type it is designed to detect (column-specific where relevant)
TEST_TO_ISSUE = {
    "dq_not_null": "null_value",
    "dq_unique": "duplicate_transaction_id",
    "dq_not_in_future": "future_timestamp",
    "dq_value_in_range": "negative_amount",
    "dq_referential_integrity": "orphan_foreign_key",
}
ISSUE_EXPLANATIONS = {
    "future_timestamp_within_grace":
        "Event time is only {skew} ahead of ingestion time: inside the {grace}-minute grace window that "
        "tolerates terminal clock drift. Missed by design (trade-off: false positives vs. recall).",
}


def issue_for_test(test_type: str, table: str, column: str) -> str | None:
    if test_type in ("dq_matches_pattern", "dq_in_reference_list"):
        if table == "transactions" and column == "currency":
            return "currency_format"
        if table == "merchants" and column == "mcc":
            return "invalid_mcc"
        return None
    if test_type == "dq_unique" and table != "transactions":
        return None
    if test_type == "dq_value_in_range" and column != "amount":
        return None
    return TEST_TO_ISSUE.get(test_type)


def load_source_tests(target: Path) -> pd.DataFrame:
    manifest = json.loads((target / "manifest.json").read_text())
    results = json.loads((target / "run_results.json").read_text())
    status = {r["unique_id"]: (r["status"], r.get("failures")) for r in results["results"]}
    rows = []
    for uid, n in manifest["nodes"].items():
        if n["resource_type"] != "test" or uid not in status:
            continue
        meta = n.get("test_metadata") or {}
        model_kw = (meta.get("kwargs") or {}).get("model", "")
        source_table = model_kw.split("source(")[1].split(")")[0].split("'")[3] if "source(" in model_kw else None
        rows.append({
            "unique_id": uid,
            "test_name": n["name"],
            "test_type": meta.get("name", "singular"),
            "layer": "raw" if source_table else "trusted",
            "table": source_table or (n.get("attached_node") or "").split(".")[-1],
            "column": n.get("column_name") or "",
            "relation": n.get("relation_name"),
            "status": status[uid][0],
            "failures": status[uid][1] or 0,
            "dimension": (n["config"].get("meta") or {}).get("dq_dimension", ""),
        })
    return pd.DataFrame(rows)


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--db", default=str(ROOT / "warehouse/payments.duckdb"))
    ap.add_argument("--answer-key", default=str(ROOT / "data/dq_answer_key.csv"))
    ap.add_argument("--raw", default=str(ROOT / "data/raw"))
    ap.add_argument("--target", default=str(ROOT / "dbt/target"))
    ap.add_argument("--grace-minutes", type=int, default=5)
    ap.add_argument("--out", default=str(ROOT / "dq/reports"))
    args = ap.parse_args()
    out = Path(args.out)
    out.mkdir(parents=True, exist_ok=True)

    tests = load_source_tests(Path(args.target))
    if tests.empty or not (tests.layer == "raw").any():
        print("No dbt test results found in dbt/target/run_results.json. Run `dbt build` or `dbt test` "
              "right before this script (other dbt commands such as `docs generate` overwrite run_results).",
              file=sys.stderr)
        return 1
    tests["issue_type"] = [issue_for_test(t, tb, c) for t, tb, c in zip(tests.test_type, tests.table, tests.column)]
    con = duckdb.connect(args.db)

    # ---- flagged record keys from stored failures ------------------------------------------
    flagged = []
    for t in tests[(tests.layer == "raw") & (tests.failures > 0)].itertuples():
        keys = con.sql(f"select distinct cast(record_key as varchar) as record_key from {t.relation}").df()
        keys["test_name"], keys["test_type"], keys["table_name"] = t.test_name, t.test_type, t.table
        keys["column_name"], keys["issue_type"] = t.column, t.issue_type
        flagged.append(keys)
    flagged = pd.concat(flagged, ignore_index=True) if flagged else pd.DataFrame(
        columns=["record_key", "test_name", "test_type", "table_name", "column_name", "issue_type"])

    ak = pd.read_csv(args.answer_key, dtype=str, keep_default_na=False)
    ak["column_name"] = ak.column_name.where(ak.issue_type != "duplicate_transaction_id", "transaction_id")
    ak = ak.drop_duplicates(["table_name", "record_key", "issue_type", "column_name"])

    # ---- recall: injected defect caught by a test designed for that issue + column -----------
    hits = flagged.dropna(subset=["issue_type"])[["table_name", "record_key", "issue_type", "column_name"]].drop_duplicates()
    hits["detected"] = True
    scored = ak.merge(hits, on=["table_name", "record_key", "issue_type", "column_name"], how="left")
    scored["detected"] = scored.detected.eq(True)

    # ---- explain misses -----------------------------------------------------------------------
    scored["miss_reason"] = ""
    misses = scored[~scored.detected]
    fut = misses[misses.issue_type == "future_timestamp"]
    if len(fut):
        con.register("fut_keys", fut[["record_key"]])
        skew = con.sql(f"""
            select t.transaction_id as record_key,
                   date_diff('second', t._loaded_at, t.timestamp) as skew_seconds
            from read_parquet('{args.raw}/transactions/*.parquet') t
            join fut_keys k on t.transaction_id = k.record_key""").df()
        skew_map = dict(zip(skew.record_key, skew.skew_seconds))
        for i in fut.index:
            s = skew_map.get(scored.at[i, "record_key"])
            if s is not None and s <= args.grace_minutes * 60:
                scored.at[i, "miss_reason"] = ISSUE_EXPLANATIONS["future_timestamp_within_grace"].format(
                    skew=f"{s // 60}m{s % 60:02d}s", grace=args.grace_minutes)
    scored.loc[~scored.detected & (scored.miss_reason == ""), "miss_reason"] = "UNEXPLAINED - investigate"

    by_issue = (scored.groupby(["table_name", "issue_type", "column_name"])
                .agg(injected=("record_key", "count"), detected=("detected", "sum")).reset_index())
    by_issue["recall"] = by_issue.detected / by_issue.injected
    by_issue["dq_dimension"] = by_issue.issue_type.map(ak.drop_duplicates("issue_type").set_index("issue_type").dq_dimension)

    # ---- precision per test -----------------------------------------------------------------
    ak_keys = set(zip(ak.table_name, ak.record_key, ak.issue_type))
    ak_any = set(zip(ak.table_name, ak.record_key))
    prec = []
    for name, g in flagged.groupby("test_name"):
        it = g.issue_type.iloc[0]
        tp = sum((tb, k, it) in ak_keys for tb, k in zip(g.table_name, g.record_key)) if it else 0
        other_defect = sum((tb, k) in ak_any for tb, k in zip(g.table_name, g.record_key)) - tp
        prec.append({"test_name": name, "test_type": g.test_type.iloc[0], "table_name": g.table_name.iloc[0],
                     "column_name": g.column_name.iloc[0], "target_issue": it or "(none injected)",
                     "flagged_records": len(g), "true_positives": tp,
                     "flagged_other_injected_defect": other_defect,
                     "unexplained_flags": len(g) - tp - other_defect})
    prec = pd.DataFrame(prec)
    prec["precision"] = prec.true_positives / prec.flagged_records

    # ---- grace sensitivity ------------------------------------------------------------------
    all_fut = ak[ak.issue_type == "future_timestamp"][["record_key"]]
    con.register("all_fut", all_fut)
    sens = con.sql(f"""
        with s as (
            select date_diff('second', t._loaded_at, t.timestamp) as skew_seconds
            from read_parquet('{args.raw}/transactions/*.parquet') t join all_fut k on t.transaction_id = k.record_key)
        select g.grace_minutes, count(*) as injected,
               sum(case when skew_seconds > g.grace_minutes * 60 then 1 else 0 end) as detected
        from s cross join (select unnest([0, 1, 2, 5, 10, 60]) as grace_minutes) g
        group by 1 order by 1""").df()
    sens = sens.astype({"grace_minutes": int, "injected": int, "detected": int})
    sens["recall"] = sens.detected / sens.injected

    # ---- expectations -----------------------------------------------------------------------
    expectations = []
    for issue in sorted(ak.issue_type.unique()):
        warned = tests[(tests.issue_type == issue) & (tests.status == "warn")]
        expectations.append((f"injected '{issue}' is flagged by >=1 raw-layer test (status=warn)", len(warned) > 0))
    trusted = tests[tests.layer == "trusted"]
    expectations.append((f"all {len(trusted)} trusted-layer tests (intermediate/marts/dq/seeds) pass",
                         bool((trusted.status == "pass").all())))
    expectations.append(("no test errored", bool((tests.status != "error").all())))
    expectations.append(("every miss has an explanation", bool((scored.miss_reason != "UNEXPLAINED - investigate").all())))
    expectations.append(("overall recall >= 98%", scored.detected.mean() >= 0.98))

    # ---- persist ----------------------------------------------------------------------------
    run_ts = datetime.now().replace(microsecond=0)
    by_issue.to_csv(out / "detection_by_issue.csv", index=False)
    prec.to_csv(out / "detection_by_test.csv", index=False)
    con.register("by_issue_df", by_issue.assign(scored_at=run_ts))
    con.sql("create schema if not exists dq")
    con.sql("create or replace table dq.dq_detection_scorecard as select * from by_issue_df")
    con.register("misses_df", scored[~scored.detected][["table_name", "record_key", "issue_type", "column_name", "miss_reason"]])
    con.sql("create or replace table dq.dq_detection_misses as select * from misses_df")

    total, det = len(scored), int(scored.detected.sum())
    def fmt(df: pd.DataFrame) -> str:
        d = df.copy()
        for c in ("recall", "precision"):
            if c in d:
                d[c] = d[c].map(lambda v: f"{v:.2%}")
        return d.to_markdown(index=False)

    miss_summary = (scored[~scored.detected].assign(reason=lambda d: d.miss_reason.str.replace(r"\d+m\d+s", "<1-4 min>", regex=True))
                    .groupby(["issue_type", "reason"]).size().reset_index(name="missed"))
    md = [
        "# Data Quality Detection Report",
        "",
        f"_Generated {run_ts} by `dq/compare_answer_key.py` from the latest dbt test artifacts. Synthetic data._",
        "",
        "## Summary",
        "",
        f"- Injected defects (answer key): **{total:,}**",
        f"- Detected by the test designed for that defect: **{det:,}**  ->  overall recall **{det / total:.2%}**",
        f"- Missed: **{total - det:,}** (all explained below)" if total - det and expectations[-2][1] else f"- Missed: **{total - det:,}**",
        f"- Raw-layer tests flagging 0 records outside the answer key: "
        f"**{int((prec.unexplained_flags == 0).sum())}/{len(prec)}** (precision {prec.true_positives.sum() / max(prec.flagged_records.sum(), 1):.2%} overall)",
        "",
        "## Expectations",
        "",
        "| Expectation | Result |",
        "|---|---|",
        *[f"| {e} | {'PASS' if ok else 'FAIL'} |" for e, ok in expectations],
        "",
        "## Recall by injected issue",
        "",
        fmt(by_issue[["dq_dimension", "table_name", "issue_type", "column_name", "injected", "detected", "recall"]]),
        "",
        "## Precision by test",
        "",
        "`flagged_other_injected_defect` = the record is defective, but under a different injected issue type "
        "(would indicate a test with overlapping scope). `unexplained_flags` = records not in the answer key at all, "
        "i.e. true false positives.",
        "",
        fmt(prec[["test_type", "table_name", "column_name", "target_issue", "flagged_records", "true_positives",
                  "flagged_other_injected_defect", "unexplained_flags", "precision"]]),
        "",
        "## Why were defects missed?",
        "",
        fmt(miss_summary) if len(miss_summary) else "_No misses._",
        "",
        "## Coverage notes (format check vs. domain check)",
        "",
        "The MCC **format** check (`[0-9]{4}`) cannot catch codes like `0000` or `1234`. They are well-formed but do not "
        "exist in ISO 18245. Those are caught only by the **reference-list** check, which is why both layers exist. "
        "Per-test catch counts:",
        "",
        fmt(prec[prec.target_issue.isin(["invalid_mcc", "currency_format"])][["test_type", "column_name", "target_issue", "true_positives"]]),
        "",
        "## Timeliness grace-window sensitivity",
        "",
        "Recall of the future-timestamp check under different clock-skew tolerances. A smaller window catches more "
        "injected skew. In production it would also flag legitimate terminals with drifting clocks, which this "
        "synthetic data does not model, so the window is a business decision, not a purely technical one.",
        "",
        fmt(sens),
        "",
    ]
    (out / "detection_report.md").write_text("\n".join(md))
    print("\n".join(md[:14]))
    print(f"\nReport: {out / 'detection_report.md'}")
    failed = [e for e, ok in expectations if not ok]
    for e in failed:
        print("EXPECTATION FAILED:", e, file=sys.stderr)
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
