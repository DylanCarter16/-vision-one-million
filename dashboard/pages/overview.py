from __future__ import annotations

import sys
from pathlib import Path

import pandas as pd
import streamlit as st

from db import get_all_metrics

_DASH = Path(__file__).resolve().parent.parent
if str(_DASH) not in sys.path:
    sys.path.insert(0, str(_DASH))

ACCENT = "#00C853"
WARN = "#FFB300"
DANGER = "#FF5252"
CARD_BG = "#1E2329"

DOMAIN_ORDER = ["housing", "transportation", "healthcare", "employment", "placemaking"]

DOMAIN_HEADLINE: dict[str, str] = {
    "housing":        "building_homes_needed",
    "transportation": "transit_ridership_target",
    "healthcare":     "er_wait_target",
    "employment":     "regional_employment",
    "placemaking":    "ghg_reduction",
}

# Human-readable unit override shown on the card below the value
DOMAIN_UNIT_LABEL: dict[str, str] = {
    "housing":        "units toward 15,000 target",
    "transportation": "monthly boardings",
    "healthcare":     "hrs ER wait (target: <3.0)",
    "employment":     "% employment rate",
    "placemaking":    "% toward GHG target",
}

# Short display label for domain cards — keeps header from wrapping
DOMAIN_LABEL: dict[str, str] = {
    "housing": "Housing",
    "transportation": "Transit",
    "healthcare": "Healthcare",
    "employment": "Employment",
    "placemaking": "Placemaking",
}

DOMAIN_ICON: dict[str, str] = {
    "housing": "🏠",
    "transportation": "🚌",
    "healthcare": "🏥",
    "employment": "💼",
    "placemaking": "🌳",
}


def _status_label(status: str) -> str:
    s = (status or "").lower()
    return {"success": "✅ success", "fallback": "⚠️ fallback", "failed": "❌ failed"}.get(s, s)


def _format_value(value: float, unit: str) -> str:
    u = (unit or "").lower()
    if u == "cad":
        return f"${value:,.0f}"
    if "trips" in u or u in ("units/yr", "units", "jobs"):
        return f"{value:,.0f}"
    if u == "hours":
        return f"{value:.1f} hrs"
    if "%" in u or u in ("percent", "vacancy_pct", "percent_employed"):
        return f"{value:.1f}%"
    return f"{value:,.2f}"


def _domain_card(col: st.delta_generator.DeltaGenerator, domain: str, df: pd.DataFrame) -> None:
    rows = df[df["domain"].str.lower() == domain]
    icon = DOMAIN_ICON.get(domain, "📊")
    display_name = DOMAIN_LABEL.get(domain, domain.title())
    n_metrics = len(rows)

    # Fixed min-height keeps all cards the same height regardless of content
    base_style = (
        f"background:{CARD_BG};border:1px solid #30363D;border-radius:14px;"
        f"padding:20px 18px;min-height:180px;display:flex;flex-direction:column;justify-content:space-between;"
    )

    if rows.empty:
        col.markdown(
            f"<div style='{base_style}'>"
            f"<p style='color:#8B949E;font-size:0.72rem;text-transform:uppercase;letter-spacing:0.07em;margin:0 0 6px;'>{icon} {display_name}</p>"
            f"<p style='color:#484F58;font-size:1rem;margin:0;'>No data</p>"
            f"</div>",
            unsafe_allow_html=True,
        )
        return

    headline_id = DOMAIN_HEADLINE.get(domain, "")
    if headline_id:
        hr = rows[rows["metric_id"] == headline_id]
        headline_row = hr.iloc[0] if not hr.empty else rows.iloc[0]
    else:
        headline_row = rows.iloc[0]

    value = pd.to_numeric(headline_row.get("value"), errors="coerce")
    unit = str(headline_row.get("unit") or "")
    status = str(headline_row.get("source_status") or "")
    ts_raw = str(headline_row.get("timestamp") or "")
    freshness = ts_raw[:10] if ts_raw else "—"
    formatted = _format_value(float(value), unit) if pd.notna(value) else "—"
    unit_label = DOMAIN_UNIT_LABEL.get(domain, unit)

    if status == "success":
        badge_color, badge_bg = "#2E7D32", "#0a2a0a"
    elif status == "fallback":
        badge_color, badge_bg = "#1565C0", "#0a1a2e"
    else:
        badge_color, badge_bg = "#C62828", "#2d0a0a"

    badge = (
        f"<span style='display:inline-block;padding:2px 8px;border-radius:10px;"
        f"background:{badge_bg};color:{badge_color};border:1px solid {badge_color}55;"
        f"font-size:0.68rem;font-weight:700;text-transform:uppercase;letter-spacing:0.04em;'>"
        f"{status or 'unknown'}</span>"
    )

    col.markdown(
        f"<div style='{base_style}'>"
        f"<div>"
        f"<p style='color:#8B949E;font-size:0.72rem;text-transform:uppercase;letter-spacing:0.07em;margin:0 0 4px;'>{icon} {display_name}</p>"
        f"<p style='color:#E6EDF3;font-size:1.75rem;font-weight:800;margin:4px 0 4px;line-height:1.1;'>{formatted}</p>"
        f"<p style='color:#8B949E;font-size:0.75rem;margin:0 0 10px;overflow:hidden;text-overflow:ellipsis;white-space:nowrap;'>{unit_label}</p>"
        f"</div>"
        f"<div style='display:flex;justify-content:space-between;align-items:center;'>"
        f"{badge}"
        f"<span style='color:#484F58;font-size:0.68rem;'>{n_metrics} metric{'s' if n_metrics!=1 else ''} · {freshness}</span>"
        f"</div>"
        f"</div>",
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

    # ── Domain health cards ──────────────────────────────────────────────────
    cols = st.columns(len(DOMAIN_ORDER), gap="small")
    for i, domain in enumerate(DOMAIN_ORDER):
        _domain_card(cols[i], domain, df)

    # ── Rating legend ────────────────────────────────────────────────────────
    st.markdown("<div style='margin-top:28px;'></div>", unsafe_allow_html=True)
    RATINGS = [
        ("NEEDS ATTENTION", "#C62828", "#3b0a0a", "< 40% of target"),
        ("IN PROGRESS",     "#F9A825", "#3b2a00", "40 – 69% of target"),
        ("ON TRACK",        "#2E7D32", "#0a2b0a", "70 – 89% of target"),
        ("ACHIEVED",        "#00838F", "#00222a", "90%+ of target"),
    ]
    badge_html = "".join(
        f"<span style='display:inline-flex;align-items:center;gap:6px;margin-right:14px;"
        f"padding:4px 12px;border-radius:10px;background:{bg};border:1px solid {color}55;"
        f"font-size:0.72rem;font-weight:700;color:{color};text-transform:uppercase;"
        f"letter-spacing:0.05em;white-space:nowrap;'>"
        f"{label} <span style='font-weight:400;color:#8B949E;font-size:0.68rem;'>{desc}</span></span>"
        for label, color, bg, desc in RATINGS
    )
    st.markdown(
        f"<div style='margin-bottom:28px;'>"
        f"<p style='color:#8B949E;font-size:0.75rem;text-transform:uppercase;letter-spacing:0.06em;"
        f"margin-bottom:8px;'>Scorecard Rating System</p>"
        f"<div style='display:flex;flex-wrap:wrap;gap:6px;'>{badge_html}</div>"
        f"</div>",
        unsafe_allow_html=True,
    )

    # ── All Latest Metrics table ─────────────────────────────────────────────
    st.markdown(
        "<h2 style='font-size:1.1rem;font-weight:700;color:#E6EDF3;margin-bottom:12px;'>All Latest Metrics</h2>",
        unsafe_allow_html=True,
    )

    display = df.copy()
    display["value"] = pd.to_numeric(display["value"], errors="coerce")
    display["Value"] = display.apply(
        lambda r: float(r["value"]) if pd.notna(r["value"]) else None,
        axis=1,
    )
    display["Last Updated"] = (
        display["timestamp"].astype(str).str[:16].str.replace("T", " ", regex=False)
    )
    display["Status"] = display["source_status"].apply(_status_label)
    display["Domain"] = display["domain"].str.title()
    display["Metric"] = display["label"].fillna(display["metric_id"])
    display["Unit"] = display["unit"].fillna("")

    table = display[["Domain", "Metric", "Value", "Unit", "Last Updated", "Status"]].copy()

    st.dataframe(
        table,
        use_container_width=True,
        hide_index=True,
        column_config={
            "Domain": st.column_config.TextColumn("Domain", width="small"),
            "Metric": st.column_config.TextColumn("Metric"),
            "Value": st.column_config.NumberColumn("Value", format="%.2f"),
            "Unit": st.column_config.TextColumn("Unit", width="small"),
            "Last Updated": st.column_config.TextColumn("Last Updated", width="medium"),
            "Status": st.column_config.TextColumn("Status", width="small"),
        },
    )
