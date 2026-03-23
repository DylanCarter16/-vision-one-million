from __future__ import annotations

import pandas as pd
import streamlit as st

from db import get_all_metrics

ACCENT = "#00C853"
WARN = "#FFB300"
DANGER = "#FF5252"
CARD_BG = "#1E2329"

DOMAIN_ORDER = ["housing", "transportation", "healthcare", "employment", "placemaking"]

# Headline metric per domain (first match wins)
DOMAIN_HEADLINE: dict[str, str] = {
    "housing": "housing_starts_total",
    "transportation": "transit_ridership",
    "healthcare": "er_wait_times",
    "employment": "unemployment_rate",
    "placemaking": "",  # no metric yet; card will show placeholder
}

DOMAIN_ICON: dict[str, str] = {
    "housing": "🏠",
    "transportation": "🚌",
    "healthcare": "🏥",
    "employment": "💼",
    "placemaking": "🌳",
}


def _badge(status: str) -> str:
    s = (status or "").lower()
    if s == "success":
        color, bg = ACCENT, "#0d2818"
    elif s == "fallback":
        color, bg = WARN, "#2d1e02"
    else:
        color, bg = DANGER, "#2d0a0a"
    return (
        f"<span style='display:inline-block;padding:2px 10px;border-radius:10px;"
        f"background:{bg};color:{color};border:1px solid {color}44;"
        f"font-size:0.7rem;font-weight:700;text-transform:uppercase;letter-spacing:0.04em;'>"
        f"{s or 'unknown'}</span>"
    )


def _format_value(value: float, unit: str) -> str:
    u = (unit or "").lower()
    if u == "cad":
        return f"${value:,.0f}"
    if "trips" in u:
        return f"{value:,.0f}"
    if u == "units":
        return f"{value:,.0f}"
    if u == "%":
        return f"{value:.1f}%"
    if u == "hours":
        return f"{value:.1f} hrs"
    return f"{value:,.2f}"


def _domain_card(col: st.delta_generator.DeltaGenerator, domain: str, df: pd.DataFrame) -> None:
    rows = df[df["domain"].str.lower() == domain]
    icon = DOMAIN_ICON.get(domain, "📊")
    n_metrics = len(rows)

    if rows.empty:
        col.markdown(
            f"""<div style='background:{CARD_BG};border:1px solid #30363D;border-radius:14px;padding:20px 18px;height:160px;'>
            <p style='color:#8B949E;font-size:0.72rem;text-transform:uppercase;letter-spacing:0.07em;margin:0 0 6px;'>{icon} {domain.title()}</p>
            <p style='color:#484F58;font-size:1.1rem;margin:0;'>No data</p>
            </div>""",
            unsafe_allow_html=True,
        )
        return

    # Pick the headline row
    headline_id = DOMAIN_HEADLINE.get(domain, "")
    if headline_id:
        hr = rows[rows["metric_id"] == headline_id]
        headline_row = hr.iloc[0] if not hr.empty else rows.iloc[0]
    else:
        headline_row = rows.iloc[0]

    value = pd.to_numeric(headline_row.get("value"), errors="coerce")
    unit = str(headline_row.get("unit") or "")
    label = str(headline_row.get("label") or headline_row.get("metric_id") or "")
    status = str(headline_row.get("source_status") or "")
    ts_raw = str(headline_row.get("timestamp") or "")
    freshness = ts_raw[:10] if ts_raw else "—"

    formatted = _format_value(float(value), unit) if pd.notna(value) else "—"

    col.markdown(
        f"""<div style='background:{CARD_BG};border:1px solid #30363D;border-radius:14px;padding:20px 18px;'>
        <p style='color:#8B949E;font-size:0.72rem;text-transform:uppercase;letter-spacing:0.07em;margin:0 0 2px;'>{icon} {domain.title()}</p>
        <p style='color:#E6EDF3;font-size:1.8rem;font-weight:800;margin:6px 0 4px;line-height:1.1;'>{formatted}</p>
        <p style='color:#8B949E;font-size:0.78rem;margin:0 0 8px;'>{label[:48]}</p>
        <div style='display:flex;justify-content:space-between;align-items:center;'>
            {_badge(status)}
            <span style='color:#484F58;font-size:0.7rem;'>{n_metrics} metric{'s' if n_metrics!=1 else ''} · {freshness}</span>
        </div>
        </div>""",
        unsafe_allow_html=True,
    )


def render() -> None:
    st.markdown(
        "<h1 style='font-size:1.6rem;font-weight:800;color:#E6EDF3;margin-bottom:4px;'>Overview</h1>"
        "<p style='color:#8B949E;font-size:0.9rem;margin-bottom:24px;'>Regional scorecard snapshot — Waterloo Region</p>",
        unsafe_allow_html=True,
    )

    df = get_all_metrics()
    if df.empty:
        st.info("No metrics in the database yet. The pipeline has not run.")
        return

    # ── Domain health cards ──
    cols = st.columns(len(DOMAIN_ORDER), gap="small")
    for i, domain in enumerate(DOMAIN_ORDER):
        _domain_card(cols[i], domain, df)

    st.markdown("<div style='margin-top:32px;'></div>", unsafe_allow_html=True)

    # ── Metrics table ──
    st.markdown(
        "<h2 style='font-size:1.1rem;font-weight:700;color:#E6EDF3;margin-bottom:12px;'>All Latest Metrics</h2>",
        unsafe_allow_html=True,
    )

    display = df.copy()
    display["value"] = pd.to_numeric(display["value"], errors="coerce")
    display["Formatted Value"] = display.apply(
        lambda r: _format_value(float(r["value"]), str(r.get("unit") or ""))
        if pd.notna(r["value"]) else "—",
        axis=1,
    )
    display["Last Updated"] = display["timestamp"].astype(str).str[:16].str.replace("T", " ")
    display["Status"] = display["source_status"].apply(_badge)

    table = display.rename(columns={"domain": "Domain", "label": "Metric", "unit": "Unit"})[
        ["Domain", "Metric", "Formatted Value", "Unit", "Last Updated", "Status"]
    ]

    # Render as HTML so status badges show colours
    html = table.to_html(escape=False, index=False, classes="metrics-table")
    st.markdown(
        f"""
        <style>
        .metrics-table {{width:100%;border-collapse:collapse;font-size:0.85rem;}}
        .metrics-table th {{background:#161B22;color:#8B949E;text-align:left;padding:10px 12px;
                           border-bottom:1px solid #30363D;text-transform:uppercase;font-size:0.72rem;letter-spacing:0.05em;}}
        .metrics-table td {{padding:10px 12px;border-bottom:1px solid #21262D;color:#E6EDF3;}}
        .metrics-table tr:hover td {{background:#21262D;}}
        </style>
        {html}
        """,
        unsafe_allow_html=True,
    )
