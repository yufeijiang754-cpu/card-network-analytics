"""Card Payment Network Analytics - Streamlit entry point.

Run from the repository root:  streamlit run dashboard/app.py
"""

import streamlit as st

st.set_page_config(page_title="Card Network Analytics", page_icon="💳", layout="wide")

pages = [
    st.Page("network_performance.py", title="Network Performance", icon="📈", default=True),
    st.Page("data_quality_monitor.py", title="Data Quality Monitor", icon="🛡️"),
]
nav = st.navigation(pages)
with st.sidebar:
    st.markdown("**Card Payment Network Analytics & Data Quality Platform**")
    st.caption("Portfolio project. All data is synthetic. Warehouse: DuckDB (dbt). "
               "See README for the architecture.")
nav.run()
