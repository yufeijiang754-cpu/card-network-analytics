"""Page 2 - Data Quality Monitor: pass-rate trends per dimension, latest run scorecard, failure drill-down."""

from __future__ import annotations

import plotly.express as px
import plotly.graph_objects as go
import streamlit as st

from db import DIMENSION_COLORS, INK_2, SERIES, STATUS, query, style, synthetic_banner, table_exists

st.title("Data Quality Monitor")
synthetic_banner()

if not table_exists("dq", "dq_results"):
    st.warning("No DQ results yet. Run `make dq` (dbt build + answer-key scoring).")
    st.stop()

ICON = {"WITHIN_THRESHOLD": "✅ Within threshold", "BREACH": "🔴 Breach", "ERROR": "⛔ Error"}
STATUS_ICON = {"pass": "✅ pass", "warn": "⚠️ warn", "fail": "🔴 fail", "error": "⛔ error"}

runs = query("""select run_id, min(run_started_at) as run_started_at, count(*) as tests
                from dq.dq_results group by 1 order by 2 desc""")
run_label = {r.run_id: f"{r.run_started_at:%Y-%m-%d %H:%M:%S}  ({r.tests} tests)" for r in runs.itertuples()}
c1, c2 = st.columns([2, 3])
run_id = c1.selectbox("dbt run", list(run_label), format_func=run_label.get)
layer = c2.radio("Layer", ["Raw sources", "Trusted layers", "All"], horizontal=True,
                 help="Raw-source tests WARN by design (they measure incoming defects). Trusted-layer tests must pass.")
layer_sql = {"Raw sources": "and model like 'raw.%'", "Trusted layers": "and model not like 'raw.%'", "All": ""}[layer]

latest = query(f"select * from dq.dq_results where run_id = ? {layer_sql} order by pass_rate", (run_id,))

# ---------------------------------------------------------------------------------------------
# KPI tiles
# ---------------------------------------------------------------------------------------------
flow = query("select dq_status, count(*) as n from intermediate.int_transactions__dq_flagged group by 1")
flow_n = dict(zip(flow.dq_status, flow.n))
raw_total = sum(flow_n.values())
k = st.columns(6)
k[0].metric("Tests executed", f"{len(latest):,}")
k[1].metric("Tests with failures", f"{(latest.failed_rows > 0).sum():,}",
            help="dbt status warn/fail: at least one failing record.")
k[2].metric("Threshold breaches", f"{(latest.threshold_status == 'BREACH').sum():,}",
            help="Pass rate below the dimension threshold (see docs/DATA_QUALITY_SCORECARD.md).")
k[3].metric("Records trusted", f"{(flow_n.get('valid', 0) + flow_n.get('repaired', 0)) / raw_total:.2%}",
            help="Share of raw records that reached the marts (valid + repaired).")
k[4].metric("Quarantined", f"{flow_n.get('quarantined', 0):,}",
            help="Blocking issues; see quarantine explorer below.")
if table_exists("dq", "dq_detection_scorecard"):
    det = query("select sum(detected) * 1.0 / sum(injected) as recall from dq.dq_detection_scorecard").recall.iat[0]
    k[5].metric("Recall vs answer key", f"{det:.2%}", help="Injected defects caught by the designed test.")

# ---------------------------------------------------------------------------------------------
# Pass-rate trend by dimension (per ingestion-day partition)
# ---------------------------------------------------------------------------------------------
grain = st.radio("Trend grain", ["Week", "Day"], horizontal=True, label_visibility="collapsed")
trend = query(f"""
    select date_trunc('{grain.lower()}', load_date) as period, dq_dimension,
           1 - sum(failed_rows) * 1.0 / sum(total_rows) as pass_rate, sum(failed_rows) as failed_rows
    from dq.dq_daily_partition_metrics
    where load_date <= (select max(cast(loaded_at as date)) from marts.fct_transactions)
    group by 1, 2 order by 1""")
thresholds = query("""select dimension, max(threshold) as threshold from dq.dq_results
                      where run_id = ? group by 1""", (run_id,))
fig = px.line(trend, x="period", y="pass_rate", color="dq_dimension", color_discrete_map=DIMENSION_COLORS,
              custom_data=["failed_rows"], category_orders={"dq_dimension": list(DIMENSION_COLORS)})
fig.update_traces(hovertemplate="%{x|%d %b %Y}<br>%{y:.3%} pass rate<br>%{customdata[0]:,} failing records<extra></extra>")
for t in thresholds.itertuples():
    if t.dimension in ("validity", "completeness"):
        fig.add_hline(y=t.threshold, line_dash="dot", line_color=DIMENSION_COLORS[t.dimension], line_width=1,
                      annotation_text=f"{t.dimension} threshold {t.threshold:.2%}", annotation_font_color=INK_2,
                      annotation_position="bottom left")
fig.update_layout(yaxis_tickformat=".2%", yaxis_title="Record pass rate", xaxis_title="Ingestion date",
                  hovermode="x unified")
st.plotly_chart(style(fig, f"Pass rate by DQ dimension, per {grain.lower()} of ingestion (row-level rules)", 380),
                use_container_width=True, theme=None)
st.caption("Each dimension's pass rate = 1 - failing records / records ingested, pooled over that dimension's rules. "
           "Dotted lines: thresholds for the two dimensions that run closest to them.")

# ---------------------------------------------------------------------------------------------
# Latest run scorecard
# ---------------------------------------------------------------------------------------------
st.subheader("Scorecard: selected run")
view = latest.assign(
    status=latest.status.map(STATUS_ICON).fillna(latest.status),
    threshold_status=latest.threshold_status.map(ICON).fillna(latest.threshold_status),
)[["model", "dimension", "check_name", "status", "failed_rows", "total_rows", "pass_rate", "threshold",
   "threshold_status"]]
st.dataframe(view, hide_index=True, use_container_width=True, height=420, column_config={
    "pass_rate": st.column_config.NumberColumn("pass rate", format="%.4f"),
    "threshold": st.column_config.NumberColumn(format="%.4f"),
    "failed_rows": st.column_config.NumberColumn("failed rows", format="%d"),
    "total_rows": st.column_config.NumberColumn("total rows", format="%d"),
})
by_dim = latest.groupby("dimension").agg(failed=("failed_rows", "sum"),
                                         breaches=("threshold_status", lambda s: (s == "BREACH").sum())).reset_index()
by_dim = by_dim.sort_values("failed")
fig = go.Figure(go.Bar(
    x=by_dim.failed, y=by_dim.dimension, orientation="h",
    marker_color=[DIMENSION_COLORS.get(d, SERIES[7]) for d in by_dim.dimension],
    text=[f"{f:,}  ({b} breach{'es' if b != 1 else ''})" for f, b in zip(by_dim.failed, by_dim.breaches)],
    textposition="outside", textfont_color=INK_2,
    hovertemplate="%{y}<br>%{x:,} failing records<extra></extra>"))
fig.update_layout(xaxis_title="Failing records (sum over checks)", yaxis_title=None, showlegend=False,
                  xaxis_range=[0, float(by_dim.failed.max() or 1) * 1.3])
st.plotly_chart(style(fig, "Failures by dimension", 320), use_container_width=True, theme=None)

# ---------------------------------------------------------------------------------------------
# Run history
# ---------------------------------------------------------------------------------------------
if len(runs) > 1:
    hist = query("""select run_started_at, dimension, 1 - sum(failed_rows) * 1.0 / sum(total_rows) as pass_rate
                    from dq.dq_results where model like 'raw.%' group by 1, 2 order by 1""")
    fig = px.line(hist, x="run_started_at", y="pass_rate", color="dimension", markers=True,
                  color_discrete_map=DIMENSION_COLORS)
    fig.update_traces(marker_size=8)
    fig.update_layout(yaxis_tickformat=".2%", xaxis_title="Run", yaxis_title="Pass rate (raw sources)")
    st.plotly_chart(style(fig, "Pass rate by dimension across dbt runs"), use_container_width=True, theme=None)

# ---------------------------------------------------------------------------------------------
# Failure drill-down
# ---------------------------------------------------------------------------------------------
st.subheader("Failure details")
failing = latest[latest.failed_rows > 0]
tab1, tab2, tab3 = st.tabs(["Failing records by check", "Quarantine explorer", "Detection vs. answer key"])
with tab1:
    if failing.empty:
        st.success("No failing checks in this selection.")
    else:
        choice = st.selectbox("Check", failing.check_name + "  ·  " + failing.model, index=0)
        row = failing[(failing.check_name + "  ·  " + failing.model) == choice].iloc[0]
        st.caption(f"Stored failures: `{row.failures_relation}` (latest run of this test, first 500 rows).")
        try:
            st.dataframe(query(f"select * from {row.failures_relation} limit 500"), hide_index=True,
                         use_container_width=True)
        except Exception as exc:  # stored-failure table may be replaced by a newer run
            st.info(f"Stored failures are not available for this run: {exc}")
with tab2:
    issues = query("""
        select issue, remediation_owner, count(*) as records from (
            select unnest(string_split(dq_issues, ' ')) as issue, remediation_owner from dq.dq_transaction_quarantine)
        group by 1, 2 order by records desc""")
    c1, c2 = st.columns([2, 3])
    fig = px.bar(issues.sort_values("records"), x="records", y="issue", orientation="h",
                 color_discrete_sequence=[SERIES[0]], text="records")
    fig.update_traces(texttemplate="%{x:,}", textposition="outside", textfont_color=INK_2,
                      hovertemplate="%{y}<br>%{x:,} quarantined records<extra></extra>")
    fig.update_layout(xaxis_title="Quarantined records", yaxis_title=None)
    c1.plotly_chart(style(fig, "Quarantine reasons", 360), use_container_width=True, theme=None)
    pick = c2.multiselect("Filter by issue", issues.issue.tolist(), default=issues.issue.tolist()[:1])
    sample = query(f"""select * from dq.dq_transaction_quarantine
                       where {' or '.join(['dq_issues like ?'] * len(pick)) if pick else 'true'}
                       order by loaded_at limit 500""", tuple(f"%{p}%" for p in pick))
    c2.dataframe(sample, hide_index=True, use_container_width=True, height=330)
with tab3:
    if table_exists("dq", "dq_detection_scorecard"):
        sc = query("""select dq_dimension, table_name, issue_type, column_name, injected, detected, recall
                      from dq.dq_detection_scorecard order by recall, injected desc""")
        st.dataframe(sc, hide_index=True, use_container_width=True, column_config={
            "recall": st.column_config.ProgressColumn(format="%.4f", min_value=0, max_value=1)})
        misses = query("select issue_type, miss_reason, count(*) as missed from dq.dq_detection_misses group by 1, 2")
        if len(misses):
            st.markdown("**Why defects were missed**")
            st.dataframe(misses, hide_index=True, use_container_width=True)
    else:
        st.info("Run `python dq/compare_answer_key.py` to score the tests against the injected answer key.")

st.markdown(
    f"<span style='color:{STATUS['good']}'>●</span> Within threshold &nbsp; "
    f"<span style='color:{STATUS['critical']}'>●</span> Breach. Thresholds and owners: "
    "`docs/DATA_QUALITY_SCORECARD.md`", unsafe_allow_html=True)
