from __future__ import annotations

import streamlit as st

from dashboard.db import get_all_metrics, get_domain_summary
from dashboard.pages import domain_detail, overview, system_health

ACCENT = "#00C853"
DOMAIN_PAGES = ["Housing", "Transportation", "Healthcare", "Employment", "Placemaking"]


def _inject_theme() -> None:
    st.markdown(
        f"""
        <style>
        .stApp {{ background-color: #0E1117; color: #ECEFF1; }}
        .metric-dot-green {{ color: {ACCENT}; font-size: 14px; }}
        .metric-dot-red {{ color: #ff5252; font-size: 14px; }}
        </style>
        """,
        unsafe_allow_html=True,
    )


def _domain_ok(domain: str) -> bool:
    df = get_domain_summary(domain)
    if df.empty:
        return False
    statuses = df["source_status"].astype(str).str.lower()
    return bool((statuses == "success").all())


def _sidebar_status() -> str:
    lines = ["### Domain Source Status"]
    for domain in [d.lower() for d in DOMAIN_PAGES]:
        ok = _domain_ok(domain)
        dot_class = "metric-dot-green" if ok else "metric-dot-red"
        lines.append(f"<span class='{dot_class}'>●</span> {domain.title()}")
    return "<br/>".join(lines)


def _last_updated_text() -> str:
    df = get_all_metrics()
    if df.empty or "timestamp" not in df.columns:
        return "No updates yet"
    ts = df["timestamp"].dropna().astype(str)
    if ts.empty:
        return "No updates yet"
    return str(ts.max())


def main() -> None:
    st.set_page_config(page_title="Vision One Million", layout="wide")
    _inject_theme()

    st.sidebar.title("Navigation")
    page = st.sidebar.radio(
        "Go to",
        ["Overview", *DOMAIN_PAGES, "System Health"],
        index=0,
    )
    st.sidebar.markdown(_sidebar_status(), unsafe_allow_html=True)

    st.title("Vision One Million")
    st.caption(f"Regional Scorecard Dashboard | Last updated: {_last_updated_text()}")

    if page == "Overview":
        overview.render()
    elif page == "System Health":
        system_health.render()
    else:
        domain_detail.render(page.lower())


if __name__ == "__main__":
    main()