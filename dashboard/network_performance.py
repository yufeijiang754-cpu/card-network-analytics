"""Page 1 - Network Performance: volume, approval, fraud and cross-border KPIs with filters."""

from __future__ import annotations

from datetime import date, timedelta

import plotly.express as px
import plotly.graph_objects as go
import streamlit as st

from db import CHANNEL_COLORS, INK_2, SERIES, query, style, synthetic_banner

st.title("Network Performance")
synthetic_banner()

# ---------------------------------------------------------------------------------------------
# Filters (one row above the charts)
# ---------------------------------------------------------------------------------------------
bounds = query("select min(transaction_date) as lo, max(transaction_date) as hi from marts.fct_transactions")
lo, hi = bounds.lo.iat[0].date(), bounds.hi.iat[0].date()
categories = query("select distinct mcc_category from marts.dim_merchant order by 1").mcc_category.tolist()
mccs = query("""select mcc, mcc_description from marts.dim_merchant where is_valid_mcc
                group by 1, 2 order by 1""")
issuers = query("select issuer_id, issuer_name from marts.dim_issuer order by issuer_id")
issuer_label = dict(zip(issuers.issuer_id, issuers.issuer_id + " - " + issuers.issuer_name))
mcc_label = dict(zip(mccs.mcc, mccs.mcc + " - " + mccs.mcc_description))

c1, c2, c3, c4, c5 = st.columns([1.3, 1.2, 1.4, 1, 1.4])
period = c1.date_input("Date range", value=(lo, hi), min_value=lo, max_value=hi)
sel_cat = c2.multiselect("MCC category", categories, placeholder="All categories")
sel_mcc = c3.multiselect("MCC", list(mcc_label), format_func=mcc_label.get, placeholder="All MCCs")
sel_channel = c4.multiselect("Channel", ["card_present", "card_not_present"], placeholder="All channels")
sel_issuer = c5.multiselect("Issuer", list(issuer_label), format_func=issuer_label.get, placeholder="All issuers")

start, end = (period if isinstance(period, tuple) and len(period) == 2 else (lo, hi))


def where(start_d: date, end_d: date) -> tuple[str, tuple]:
    clauses, params = ["transaction_date between ? and ?"], [start_d, end_d]
    for col, values in (("mcc_category", sel_cat), ("mcc", sel_mcc), ("channel", sel_channel), ("issuer_id", sel_issuer)):
        if values:
            clauses.append(f"{col} in ({', '.join('?' * len(values))})")
            params.extend(values)
    return " and ".join(clauses), tuple(params)


W, P = where(start, end)

# ---------------------------------------------------------------------------------------------
# KPI tiles (with delta vs. the preceding period of equal length)
# ---------------------------------------------------------------------------------------------
KPI_SQL = """
select count(*)                                                                  as attempts,
       sum(approved_amount_usd)                                                  as approved_usd,
       avg(case when is_approved then 1.0 else 0 end)                            as approval_rate,
       sum(fraud_loss_amount_usd) * 10000 / nullif(sum(approved_amount_usd), 0)  as fraud_bps,
       avg(case when is_fraud then 1.0 else 0 end) * 10000                       as fraud_attempt_bps,
       avg(case when is_cross_border then 1.0 else 0 end)                        as xb_share,
       sum(interchange_fee_usd)                                                  as interchange_usd
from marts.fct_transactions where {w}"""
cur = query(KPI_SQL.format(w=W), P).iloc[0]
span = (end - start).days + 1
prev_start, prev_end = start - timedelta(days=span), start - timedelta(days=1)
prev = query(KPI_SQL.format(w=where(prev_start, prev_end)[0]), where(prev_start, prev_end)[1]).iloc[0] \
    if prev_start >= lo else None

if not cur.attempts:
    st.warning("No transactions match the selected filters.")
    st.stop()


def delta(field, fmt, scale=1.0):
    if prev is None or not prev.attempts or prev[field] is None:
        return None
    return fmt.format((cur[field] - prev[field]) * scale)


k = st.columns(6)
k[0].metric("Transactions", f"{cur.attempts:,.0f}", delta(
    "attempts", "{:+,.0f}"), help="Authorization attempts (approved + declined).")
k[1].metric("Approved volume", f"${cur.approved_usd / 1e6:,.2f}M", delta("approved_usd", "{:+,.2f}M", 1e-6))
k[2].metric("Approval rate", f"{cur.approval_rate:.2%}", delta("approval_rate", "{:+.2f} pp", 100),
            help="Approved / all attempts.")
k[3].metric("Fraud loss rate", f"{cur.fraud_bps:,.1f} bps", delta("fraud_bps", "{:+.1f} bps"),
            delta_color="inverse", help="Approved fraud USD / approved USD x 10,000.")
k[4].metric("Cross-border share", f"{cur.xb_share:.2%}", delta("xb_share", "{:+.2f} pp", 100),
            delta_color="off", help="Share of attempts where card country != merchant country.")
k[5].metric("Interchange", f"${cur.interchange_usd / 1e3:,.0f}K", delta("interchange_usd", "{:+,.0f}K", 1e-3))
if prev is not None:
    st.caption(f"Deltas compare with the preceding {span}-day period ({prev_start} to {prev_end}).")

# ---------------------------------------------------------------------------------------------
# Volume & approval over time (separate charts: different units never share an axis)
# ---------------------------------------------------------------------------------------------
left, right = st.columns(2)
daily = query(f"""
    select transaction_date, count(*) as attempts
    from marts.fct_transactions where {W} group by 1 order by 1""", P)
daily["7-day average"] = daily.attempts.rolling(7, min_periods=1).mean()
fig = go.Figure()
fig.add_scatter(x=daily.transaction_date, y=daily.attempts, name="Daily", line=dict(color=SERIES[0], width=1),
                opacity=0.45, hovertemplate="%{x|%a %d %b %Y}<br>%{y:,} transactions<extra></extra>")
fig.add_scatter(x=daily.transaction_date, y=daily["7-day average"], name="7-day average",
                line=dict(color=SERIES[0], width=2), hovertemplate="7-day avg %{y:,.0f}<extra></extra>")
fig.update_layout(hovermode="x unified", yaxis_title="Transactions")
left.plotly_chart(style(fig, "Daily transaction volume"), use_container_width=True, theme=None)

weekly = query(f"""
    select date_trunc('week', transaction_date) as week, channel,
           avg(case when is_approved then 1.0 else 0 end) as approval_rate, count(*) as attempts
    from marts.fct_transactions where {W} group by 1, 2 order by 1""", P)
fig = px.line(weekly, x="week", y="approval_rate", color="channel", color_discrete_map=CHANNEL_COLORS,
              custom_data=["attempts"])
fig.update_traces(hovertemplate="Week of %{x|%d %b}<br>%{y:.2%} approved<br>%{customdata[0]:,} attempts<extra></extra>")
fig.update_layout(yaxis_tickformat=".0%", yaxis_title="Approval rate", xaxis_title=None, hovermode="x unified")
right.plotly_chart(style(fig, "Weekly approval rate by channel"), use_container_width=True, theme=None)

# ---------------------------------------------------------------------------------------------
# Fraud & cross-border
# ---------------------------------------------------------------------------------------------
left, right = st.columns(2)
seg = query(f"""
    select channel, case when is_cross_border then 'Cross-border' else 'Domestic' end as geography,
           sum(fraud_loss_amount_usd) * 10000 / nullif(sum(approved_amount_usd), 0) as fraud_bps,
           avg(case when is_fraud then 1.0 else 0 end) * 10000 as attempt_bps, count(*) as attempts
    from marts.fct_transactions where {W} group by 1, 2 order by 1, 2""", P)
fig = px.bar(seg, x="geography", y="fraud_bps", color="channel", barmode="group", color_discrete_map=CHANNEL_COLORS,
             text_auto=".0f", custom_data=["attempt_bps", "attempts"])
fig.update_traces(textposition="outside", textfont_color=INK_2,
                  hovertemplate="%{x}<br>Fraud loss %{y:.1f} bps<br>Fraud attempts %{customdata[0]:.1f} bps"
                                "<br>%{customdata[1]:,} attempts<extra></extra>")
fig.update_layout(yaxis_title="Fraud loss rate (bps)", xaxis_title=None,
                  yaxis_range=[0, float(seg.fraud_bps.max() or 1) * 1.15])
left.plotly_chart(style(fig, "Fraud loss rate by channel and geography"), use_container_width=True, theme=None)

monthly = query(f"""
    select cast(date_trunc('month', transaction_date) as date) as month,
           avg(case when is_cross_border then 1.0 else 0 end) as xb_share,
           sum(case when is_cross_border then approved_amount_usd else 0 end) / nullif(sum(approved_amount_usd), 0) as xb_volume_share
    from marts.fct_transactions where {W} group by 1 order by 1""", P)
fig = go.Figure()
fig.add_scatter(x=monthly.month, y=monthly.xb_share, name="Share of transactions", mode="lines+markers",
                line_color=SERIES[0], marker_size=8, hovertemplate="%{x|%b %Y}: %{y:.2%} of transactions<extra></extra>")
fig.add_scatter(x=monthly.month, y=monthly.xb_volume_share, name="Share of approved USD", mode="lines+markers",
                line_color=SERIES[1], marker_size=8, hovertemplate="%{x|%b %Y}: %{y:.2%} of approved USD<extra></extra>")
fig.update_layout(yaxis_tickformat=".0%", yaxis_title="Cross-border share", yaxis_rangemode="tozero")
right.plotly_chart(style(fig, "Cross-border share by month"), use_container_width=True, theme=None)

# ---------------------------------------------------------------------------------------------
# Approval by MCC category & decline reasons
# ---------------------------------------------------------------------------------------------
left, right = st.columns(2)
by_cat = query(f"""
    select mcc_category, count(*) as attempts, avg(case when is_approved then 1.0 else 0 end) as approval_rate
    from marts.fct_transactions where {W} group by 1 order by approval_rate""", P)
fig = px.bar(by_cat, x="approval_rate", y="mcc_category", orientation="h", custom_data=["attempts"],
             color_discrete_sequence=[SERIES[0]], text="approval_rate")
fig.update_traces(texttemplate="%{x:.1%}", textposition="outside", textfont_color=INK_2,
                  hovertemplate="%{y}<br>%{x:.2%} approved<br>%{customdata[0]:,} attempts<extra></extra>")
x_min = max(0.0, float(by_cat.approval_rate.min()) - 0.03)
fig.update_layout(xaxis_tickformat=".0%", xaxis_range=[x_min, 1.0], xaxis_title="Approval rate", yaxis_title=None,
                  showlegend=False)
left.plotly_chart(style(fig, "Approval rate by MCC category (axis does not start at 0)",
                        height=380), use_container_width=True, theme=None)

reasons = query(f"""
    select decline_reason, decline_type, count(*) as declines
    from marts.fct_transactions where {W} and not is_approved group by 1, 2 order by declines""", P)
reasons["share"] = reasons.declines / reasons.declines.sum()
fig = px.bar(reasons, x="declines", y="decline_reason", orientation="h", color="decline_type",
             color_discrete_map={"soft": SERIES[0], "hard": SERIES[1]}, custom_data=["share"])
fig.update_traces(hovertemplate="%{y}<br>%{x:,} declines (%{customdata[0]:.1%})<extra></extra>")
fig.update_layout(xaxis_title="Declines", yaxis_title=None, legend_title_text="Decline type")
right.plotly_chart(style(fig, "Decline reasons (soft = retryable, hard = do not retry)", height=380),
                   use_container_width=True, theme=None)

# ---------------------------------------------------------------------------------------------
# Issuer league table
# ---------------------------------------------------------------------------------------------
st.subheader("Issuer performance")
iss = query(f"""
    select f.issuer_id as "Issuer", i.issuer_name as "Name", i.issuer_country as "Country",
           count(*) as "Attempts",
           avg(case when f.is_approved then 1.0 else 0 end) as "Approval rate",
           sum(case when f.channel = 'card_not_present' and f.is_approved then 1 else 0 end) * 1.0
             / nullif(sum(case when f.channel = 'card_not_present' then 1 else 0 end), 0) as "CNP approval rate",
           sum(f.fraud_loss_amount_usd) * 10000 / nullif(sum(f.approved_amount_usd), 0) as "Fraud loss (bps)",
           sum(case when f.auth_response_code = '91' then 1 else 0 end) as "Issuer-unavailable declines"
    from marts.fct_transactions f join marts.dim_issuer i on f.issuer_id = i.issuer_id
    where {W.replace('issuer_id', 'f.issuer_id')}
    group by 1, 2, 3 order by "Attempts" desc""", P)
st.dataframe(
    iss, hide_index=True, use_container_width=True,
    column_config={
        "Attempts": st.column_config.NumberColumn(format="%d"),
        "Approval rate": st.column_config.ProgressColumn(format="%.3f", min_value=0.7, max_value=1.0),
        "CNP approval rate": st.column_config.ProgressColumn(format="%.3f", min_value=0.7, max_value=1.0),
        "Fraud loss (bps)": st.column_config.NumberColumn(format="%.1f"),
    },
)
with st.expander("Metric definitions"):
    st.markdown("""
- **Approval rate**: approved authorizations / all attempts (response code `00`).
- **Fraud loss rate (bps)**: USD of approved transactions later confirmed fraudulent / approved USD x 10,000.
- **Fraud attempt rate (bps)**: fraudulent attempts (approved or declined) / all attempts x 10,000.
- **Cross-border**: card issuing country differs from merchant country.
- **Interchange**: fee paid by the acquirer to the issuer on approved transactions (illustrative rates).
- Source: `marts.fct_transactions` (only DQ-passed records). Full definitions: dbt docs.
""")
