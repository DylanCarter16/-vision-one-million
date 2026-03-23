from __future__ import annotations

import sys
from pathlib import Path

import pandas as pd
import plotly.express as px
import streamlit as st

# Resolve scorecard_data from the dashboard/ directory
_DASH = Path(__file__).resolve().parent.parent
if str(_DASH) not in sys.path:
    sys.path.insert(0, str(_DASH))

from db import get_all_metrics, get_metric_history  # noqa: E402
from scorecard_data import (  # noqa: E402
    DOMAIN_COLOR,
    DOMAIN_ICON,
    DOMAIN_PRIMARY_METRIC,
    METRICS_BY_DOMAIN,
    get_rating,
    pct_achieved,
)

BG = "#0D1117"
CARD_BG = "#1E2329"


def _fmt(value: float, unit: str) -> str:
    u = (unit or "").lower()
    if u == "cad":
        return f"${value:,.0f}"
    if u in ("units/yr", "units", "jobs"):
        return f"{value:,.0f}"
    if "trips" in u:
        return f"{value:,.0f}"
    if u == "hours":
        return f"{value:.1f} hrs"
    if "%" in u or u in ("percent", "vacancy_pct", "percent_employed"):
        return f"{value:.1f}%"
    return f"{value:,.2f}"


def _overall_badge(avg_pct: float) -> str:
    label, color, bg = get_rating(avg_pct)
    return (
        f"<span style='display:inline-block;padding:4px 14px;border-radius:12px;"
        f"background:{bg};color:{color};border:1px solid {color}66;"
        f"font-size:0.8rem;font-weight:800;text-transform:uppercase;letter-spacing:0.06em;'>"
        f"{label} &nbsp;·&nbsp; {avg_pct:.0f}% avg</span>"
    )


_SOURCE_LABEL: dict[str, str] = {
    "success":  "✅ Live source — direct fetch",
    "fallback": "🔍 Tavily web search — primary source unavailable",
    "failed":   "❌ Data unavailable",
}


def _unit_suffix(unit: str) -> str:
    """Return a short human-readable unit label to append after a number."""
    u = (unit or "").lower()
    if u in ("units/yr", "units"):
        return " units"
    if "trips" in u:
        return " trips"
    if u == "jobs":
        return " jobs"
    if u == "km":
        return " km"
    if u in ("hours",):
        return " hrs"
    # percent-like units carry their own symbol via _fmt — no extra suffix
    return ""


def _value_line(current: float, target: float, unit: str, pct: float) -> str:
    """
    Build the value/target display line for a card.

    For percentage metrics: "54% of goal  (54.2 / 100.0%)"
    For all others:          "1,800,255 trips / 2,000,000 trips target"
    """
    u = (unit or "").lower()
    is_pct = "%" in u or u in ("percent", "vacancy_pct", "percent_employed")
    if is_pct:
        curr_fmt = _fmt(current, unit)
        tgt_fmt = _fmt(target, unit)
        return (
            f"<span style='color:#8B949E;font-size:0.72rem;'>"
            f"<strong style='color:#C9D1D9;'>{pct:.0f}%</strong> of goal"
            f"&nbsp;&nbsp;"
            f"<span style='color:#484F58;'>({curr_fmt} / {tgt_fmt})</span>"
            f"</span>"
        )
    suffix = _unit_suffix(unit)
    if u == "cad":
        curr_str = f"${current:,.0f}"
        tgt_str = f"${target:,.0f}"
        return (
            f"<span style='color:#C9D1D9;font-size:0.72rem;font-weight:700;'>{curr_str}</span>"
            f"<span style='color:#484F58;font-size:0.72rem;'> / {tgt_str} target</span>"
        )
    curr_str = f"{current:,.0f}{suffix}"
    tgt_str = f"{target:,.0f}{suffix}"
    return (
        f"<span style='color:#C9D1D9;font-size:0.72rem;font-weight:700;'>{curr_str}</span>"
        f"<span style='color:#484F58;font-size:0.72rem;'> / {tgt_str} target</span>"
    )


def _subcategory_card(
    label: str,
    current: float,
    target: float,
    unit: str,
    domain_color: str,
    pct: float,
    source_status: str = "",
) -> str:
    rating_label, rating_color, rating_bg = get_rating(pct)
    src_text = _SOURCE_LABEL.get((source_status or "").lower(), "❌ Data unavailable")
    val_line = _value_line(current, target, unit, pct)
    return f"""
<div style="border-radius:12px;overflow:hidden;box-shadow:0 2px 8px #00000044;display:flex;flex-direction:column;">
  <div style="background:{domain_color};padding:12px 14px;min-height:60px;display:flex;align-items:flex-start;">
    <span style="color:#fff;font-size:0.82rem;font-weight:700;text-transform:uppercase;letter-spacing:0.04em;line-height:1.3;word-wrap:break-word;overflow-wrap:break-word;">{label}</span>
  </div>
  <div style="background:{rating_bg};padding:8px 14px;border-top:2px solid {rating_color};">
    <div style="display:flex;justify-content:space-between;align-items:center;margin-bottom:4px;">
      <span style="color:{rating_color};font-size:0.72rem;font-weight:800;text-transform:uppercase;letter-spacing:0.06em;">{rating_label}</span>
    </div>
    <div style="margin-bottom:4px;">{val_line}</div>
    <div style="margin-top:2px;color:#484F58;font-size:0.63rem;">{src_text}</div>
  </div>
</div>"""


def render(domain: str) -> None:
    domain_color = DOMAIN_COLOR.get(domain, "#1E2329")
    icon = DOMAIN_ICON.get(domain, "📊")
    metrics_def = METRICS_BY_DOMAIN.get(domain, [])

    # Header
    st.markdown(
        f"<div style='border-left:4px solid {domain_color};padding-left:14px;margin-bottom:6px;'>"
        f"<h1 style='font-size:1.6rem;font-weight:800;color:#E6EDF3;margin:0;'>{icon} {domain.title()}</h1>"
        f"<p style='color:#8B949E;font-size:0.9rem;margin:4px 0 0;'>Vision One Million Scorecard</p>"
        f"</div>",
        unsafe_allow_html=True,
    )

    if not metrics_def:
        st.info(f"No scorecard metrics defined for domain: {domain}")
        return

    # Pull latest values from DB
    all_df = get_all_metrics()
    domain_df = all_df[all_df["domain"].str.lower() == domain].copy() if not all_df.empty else pd.DataFrame()

    def _current(metric_id: str, fallback: float) -> float:
        if not domain_df.empty:
            row = domain_df[domain_df["metric_id"] == metric_id]
            if not row.empty:
                v = pd.to_numeric(row.iloc[0]["value"], errors="coerce")
                if pd.notna(v):
                    return float(v)
        return fallback

    def _source_status(metric_id: str) -> str:
        if not domain_df.empty:
            row = domain_df[domain_df["metric_id"] == metric_id]
            if not row.empty:
                return str(row.iloc[0].get("source_status") or "")
        return "failed"

    # Calculate % achieved for each subcategory
    pcts: list[float] = []
    for m in metrics_def:
        cur = _current(m.metric_id, m.current)
        pcts.append(pct_achieved(m.metric_id, cur))

    avg_pct = sum(pcts) / len(pcts) if pcts else 0.0
    on_track_count = sum(1 for p in pcts if p >= 70)

    # Overall status badge
    st.markdown(
        f"<div style='margin:10px 0 20px;'>{_overall_badge(avg_pct)}</div>",
        unsafe_allow_html=True,
    )

    # ── Subcategory cards (3 per row) ────────────────────────────────────────
    st.markdown(
        "<h2 style='font-size:1rem;font-weight:700;color:#E6EDF3;margin-bottom:12px;'>Initiatives</h2>",
        unsafe_allow_html=True,
    )

    cards_per_row = 3
    for row_start in range(0, len(metrics_def), cards_per_row):
        row_metrics = metrics_def[row_start : row_start + cards_per_row]
        # Always create 3 columns so padding slots exist for partial last rows
        cols = st.columns(cards_per_row, gap="small")
        for i, m in enumerate(row_metrics):
            cur = _current(m.metric_id, m.current)
            p = pct_achieved(m.metric_id, cur)
            cols[i].markdown(
                _subcategory_card(
                    m.label, cur, m.target, m.unit, domain_color, p,
                    source_status=_source_status(m.metric_id),
                ),
                unsafe_allow_html=True,
            )
        # Fill remaining empty slots in last row only if needed
        remainder = len(metrics_def) % cards_per_row
        is_last_row = row_start + cards_per_row >= len(metrics_def)
        if is_last_row and remainder != 0:
            for _ in range(cards_per_row - remainder):
                cols[remainder + _].empty()

    # ── Summary line ─────────────────────────────────────────────────────────
    st.markdown(
        f"<p style='color:#8B949E;font-size:0.85rem;margin:16px 0 28px;'>"
        f"<strong style='color:#E6EDF3;'>{on_track_count}</strong> of "
        f"<strong style='color:#E6EDF3;'>{len(metrics_def)}</strong> "
        f"initiatives On Track or better</p>",
        unsafe_allow_html=True,
    )

    # ── Historical trend chart with initiative selector ───────────────────────
    st.markdown(
        "<h2 style='font-size:1rem;font-weight:700;color:#E6EDF3;margin-bottom:4px;'>Historical Trend</h2>",
        unsafe_allow_html=True,
    )

    label_to_metric = {m.label: m.metric_id for m in metrics_def}
    labels = [m.label for m in metrics_def]

    # Default to whichever label maps to the primary metric; fall back to first
    primary_id = DOMAIN_PRIMARY_METRIC.get(domain, "")
    default_label = next(
        (m.label for m in metrics_def if m.metric_id == primary_id),
        labels[0] if labels else "",
    )
    default_idx = labels.index(default_label) if default_label in labels else 0

    selected_label = st.selectbox(
        "Select initiative to view trend:",
        options=labels,
        index=default_idx,
        key=f"trend_select_{domain}",
    )

    chart_metric = label_to_metric.get(selected_label, "")

    if chart_metric:
        hist = get_metric_history(chart_metric)
        hist["value"] = pd.to_numeric(hist["value"], errors="coerce")
        hist = hist.dropna(subset=["value"])

        if len(hist) < 2:
            st.info(
                "Not enough historical data yet — check back after the next pipeline run.",
                icon="📊",
            )
        else:
            hist = hist.copy()
            hist["date"] = pd.to_datetime(
                {
                    "year": pd.to_numeric(hist["year"], errors="coerce").fillna(1970).astype(int),
                    "month": pd.to_numeric(hist["month"], errors="coerce").fillna(1).astype(int),
                    "day": 1,
                },
                errors="coerce",
            )
            hist = hist.sort_values("date")

            chart_title = f"{selected_label} — Historical Trend"
            fig = px.line(hist, x="date", y="value", markers=True,
                          title=chart_title, template="plotly_dark")
            fig.update_traces(
                line=dict(color=domain_color, width=2.5),
                marker=dict(color=domain_color, size=7),
            )
            fig.update_layout(
                paper_bgcolor=BG, plot_bgcolor=CARD_BG,
                font=dict(color="#8B949E"),
                title_font=dict(color="#E6EDF3", size=13),
                xaxis=dict(gridcolor="#21262D", linecolor="#30363D"),
                yaxis=dict(gridcolor="#21262D", linecolor="#30363D"),
                margin=dict(l=0, r=0, t=40, b=0),
            )
            st.plotly_chart(fig, use_container_width=True)
