from __future__ import annotations

import pandas as pd
import plotly.express as px
import streamlit as st

from db import get_domain_summary, get_metric_history

ACCENT = "#00C853"
CARD_BG = "#1E2329"
BG = "#0D1117"


def _badge(status: str) -> str:
    s = (status or "").lower()
    color = "#00C853" if s == "success" else ("#FFB300" if s == "fallback" else "#FF5252")
    bg = "#0d2818" if s == "success" else ("#2d1e02" if s == "fallback" else "#2d0a0a")
    return (
        f"<span style='display:inline-block;padding:2px 10px;border-radius:10px;"
        f"background:{bg};color:{color};border:1px solid {color}44;"
        f"font-size:0.7rem;font-weight:700;text-transform:uppercase;letter-spacing:0.04em;'>"
        f"{s or 'unknown'}</span>"
    )


def render(domain: str) -> None:
    st.markdown(
        f"<h1 style='font-size:1.6rem;font-weight:800;color:#E6EDF3;margin-bottom:4px;'>{domain.title()}</h1>"
        f"<p style='color:#8B949E;font-size:0.9rem;margin-bottom:20px;'>Historical trend & raw data</p>",
        unsafe_allow_html=True,
    )

    domain_df = get_domain_summary(domain)
    if domain_df.empty:
        st.info(f"No metrics found for domain: {domain}")
        return

    flagged = domain_df["flagged"].fillna(0).astype(int).gt(0).any()
    if flagged:
        st.warning("⚠️ One or more metrics in this domain are flagged for analyst review.")

    metric_ids = sorted(domain_df["metric_id"].dropna().astype(str).unique().tolist())
    metric_id = st.selectbox(
        "Select metric",
        metric_ids,
        index=0,
        key=f"select_{domain}",
    )

    # Current value card
    cur_row = domain_df[domain_df["metric_id"] == metric_id]
    if not cur_row.empty:
        r = cur_row.iloc[0]
        val = pd.to_numeric(r.get("value"), errors="coerce")
        unit = str(r.get("unit") or "")
        label = str(r.get("label") or metric_id)
        status = str(r.get("source_status") or "")
        ts = str(r.get("timestamp") or "")[:16].replace("T", " ")
        val_str = f"{float(val):,.2f} {unit}" if pd.notna(val) else "—"
        st.markdown(
            f"""<div style='background:{CARD_BG};border:1px solid #30363D;border-radius:12px;padding:18px 22px;margin-bottom:20px;'>
            <p style='color:#8B949E;font-size:0.72rem;text-transform:uppercase;letter-spacing:0.07em;margin:0 0 4px;'>Current value</p>
            <p style='color:#E6EDF3;font-size:2rem;font-weight:800;margin:0 0 6px;'>{val_str}</p>
            <p style='color:#8B949E;font-size:0.78rem;margin:0 0 10px;'>{label}</p>
            {_badge(status)} <span style='color:#484F58;font-size:0.72rem;margin-left:8px;'>Updated {ts}</span>
            </div>""",
            unsafe_allow_html=True,
        )

    # History
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
        title=f"{metric_id} — Historical Trend",
        template="plotly_dark",
    )
    fig.update_traces(
        line=dict(color=ACCENT, width=2.5),
        marker=dict(color=ACCENT, size=7),
    )
    fig.update_layout(
        paper_bgcolor=BG,
        plot_bgcolor=CARD_BG,
        font=dict(color="#8B949E"),
        title_font=dict(color="#E6EDF3", size=14),
        xaxis=dict(gridcolor="#21262D", linecolor="#30363D"),
        yaxis=dict(gridcolor="#21262D", linecolor="#30363D"),
        margin=dict(l=0, r=0, t=40, b=0),
    )
    st.plotly_chart(fig, use_container_width=True)

    # Raw table
    st.markdown(
        "<h3 style='font-size:1rem;font-weight:700;color:#E6EDF3;margin:20px 0 10px;'>Raw Data</h3>",
        unsafe_allow_html=True,
    )
    table = hist[["year", "month", "value", "unit", "source_status", "flagged", "timestamp"]].copy()
    table["timestamp"] = table["timestamp"].astype(str).str[:16].str.replace("T", " ")
    st.dataframe(table.rename(columns={
        "year": "Year", "month": "Month", "value": "Value",
        "unit": "Unit", "source_status": "Status",
        "flagged": "Flagged", "timestamp": "Timestamp",
    }), use_container_width=True, hide_index=True)
