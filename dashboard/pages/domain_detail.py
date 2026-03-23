from __future__ import annotations

import pandas as pd
import plotly.express as px
import streamlit as st

from dashboard.db import get_domain_summary, get_metric_history

ACCENT = "#00C853"


def render(domain: str) -> None:
    st.subheader(f"{domain.title()} Domain")
    domain_df = get_domain_summary(domain)
    if domain_df.empty:
        st.info(f"No metrics found for domain: {domain}")
        return

    if domain_df["flagged"].fillna(0).astype(int).gt(0).any():
        st.warning("One or more metrics in this domain are flagged for review.")

    metric_ids = sorted(domain_df["metric_id"].dropna().astype(str).unique().tolist())
    metric_id = st.selectbox("Select metric", metric_ids, index=0)

    hist = get_metric_history(metric_id)
    if hist.empty:
        st.info("No historical data available for this metric.")
        return

    hist = hist.copy()
    hist["year"] = pd.to_numeric(hist["year"], errors="coerce")
    hist["month"] = pd.to_numeric(hist["month"], errors="coerce")
    hist["value"] = pd.to_numeric(hist["value"], errors="coerce")
    hist["date"] = pd.to_datetime(
        {
            "year": hist["year"].fillna(1970).astype(int),
            "month": hist["month"].fillna(1).astype(int),
            "day": 1,
        },
        errors="coerce",
    )
    hist = hist.sort_values("date")

    fig = px.line(
        hist,
        x="date",
        y="value",
        markers=True,
        title=f"Historical Trend: {metric_id}",
        template="plotly_dark",
    )
    fig.update_traces(line_color=ACCENT, marker_color=ACCENT)
    fig.update_layout(paper_bgcolor="#0E1117", plot_bgcolor="#0E1117")
    st.plotly_chart(fig, use_container_width=True)

    table = hist[["year", "month", "value", "unit", "source_status", "flagged", "timestamp"]].copy()
    st.dataframe(table, use_container_width=True)
