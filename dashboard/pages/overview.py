from __future__ import annotations

import sys
from pathlib import Path

import pandas as pd
import streamlit as st

from db import get_all_metrics

_DASH = Path(__file__).resolve().parent.parent
if str(_DASH) not in sys.path:
    sys.path.insert(0, str(_DASH))

from scorecard_data import METRIC_BY_ID, METRICS_BY_DOMAIN, get_rating, pct_achieved  # noqa: E402

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


def _domain_avg_pct(domain: str, df: pd.DataFrame) -> float:
    """Average % of target achieved (each capped at 100) across all metrics for a domain."""
    metrics_def = METRICS_BY_DOMAIN.get(domain, [])
    if not metrics_def:
        return 0.0
    domain_df = df[df["domain"].str.lower() == domain] if not df.empty else pd.DataFrame()
    pcts: list[float] = []
    for m in metrics_def:
        cur = m.current
        if not domain_df.empty:
            row = domain_df[domain_df["metric_id"] == m.metric_id]
            if not row.empty:
                v = pd.to_numeric(row.iloc[0]["value"], errors="coerce")
                if pd.notna(v):
                    cur = float(v)
        pcts.append(pct_achieved(m.metric_id, cur))
    return round(sum(pcts) / len(pcts), 1) if pcts else 0.0


def _hex_to_rgba(hex_color: str, alpha: float) -> str:
    h = hex_color.lstrip("#")
    r, g, b = int(h[0:2], 16), int(h[2:4], 16), int(h[4:6], 16)
    return f"rgba({r},{g},{b},{alpha})"


def _context_line(domain: str, rows: pd.DataFrame) -> str:
    """One-line context string showing the key metric value vs target."""
    headline_id = DOMAIN_HEADLINE.get(domain, "")
    if not headline_id or rows.empty:
        return ""
    hr = rows[rows["metric_id"] == headline_id]
    if hr.empty:
        return ""
    row = hr.iloc[0]
    value = pd.to_numeric(row.get("value"), errors="coerce")
    unit = str(row.get("unit") or "")
    m = METRIC_BY_ID.get(headline_id)
    if m is None or pd.isna(value):
        return ""
    val = float(value)
    u = unit.lower()
    if u == "hours":
        return f"{val:.1f} hrs ER wait (target: &lt;{m.target:.1f})"
    if u in ("percent", "vacancy_pct", "percent_employed"):
        return f"{val:.1f}% (target: {m.target:.0f}%)"
    if "trips" in u:
        curr_m, tgt_m = val / 1_000_000, m.target / 1_000_000
        return f"{curr_m:.1f}M / {tgt_m:.1f}M monthly boardings"
    curr_str = f"{int(val):,}" if val == int(val) else f"{val:,.1f}"
    tgt_str  = f"{int(m.target):,}" if m.target == int(m.target) else f"{m.target:,.1f}"
    ul = DOMAIN_UNIT_LABEL.get(domain, unit)
    return f"{curr_str} / {tgt_str} {ul}"


def _card_html(domain: str, df: pd.DataFrame, avg_pct: float,
               rating_label: str, rating_color: str) -> str:
    """Inner HTML for one domain card showing avg % prominently + key metric context."""
    rows = df[df["domain"].str.lower() == domain]
    icon = DOMAIN_ICON.get(domain, "📊")
    display_name = DOMAIN_LABEL.get(domain, domain.title()).upper()
    n_initiatives = len(METRICS_BY_DOMAIN.get(domain, []))

    if rows.empty:
        return (
            f"<p style='color:#8B949E;font-size:11px;font-weight:700;text-transform:uppercase;"
            f"letter-spacing:0.1em;margin:0 0 8px;'>{icon} {display_name}</p>"
            f"<p style='color:#484F58;font-size:13px;margin:0;'>No data</p>"
        )

    ts_raw = str(rows.iloc[0].get("timestamp") or "")
    freshness = ts_raw[:10] if ts_raw else "—"
    context = _context_line(domain, rows)
    badge_bg = _hex_to_rgba(rating_color, 0.15)

    return f"""
<p style='color:#8B949E;font-size:10px;font-weight:700;text-transform:uppercase;
letter-spacing:0.1em;margin:0 0 4px;white-space:nowrap;overflow:hidden;text-overflow:ellipsis;'>
{icon} {display_name}
<span style='font-weight:400;color:#484F58;font-size:9px;margin-left:4px;'>{n_initiatives} initiatives</span>
</p>
<p style='color:#E6EDF3;font-size:30px;font-weight:800;margin:0 0 0px;line-height:1.0;'>{avg_pct:.0f}%</p>
<p style='color:#8B949E;font-size:9.5px;margin:0 0 4px;'>avg of goal</p>
<p style='color:#8B949E;font-size:10px;margin:0 0 8px;white-space:nowrap;overflow:hidden;
text-overflow:ellipsis;'>{context}</p>
<div style='margin-top:auto;'>
  <span style='display:inline-block;padding:2px 6px;border-radius:7px;
  background:{badge_bg};color:{rating_color};border:1px solid {rating_color}55;
  font-size:9.5px;font-weight:700;text-transform:uppercase;letter-spacing:0.04em;
  white-space:nowrap;'>{rating_label}</span>
  <span style='color:#484F58;font-size:9px;margin-left:6px;'>Updated: {freshness}</span>
</div>"""


def _domain_cards_row(df: pd.DataFrame) -> str:
    """Render all 5 domain cards as a single flex-row HTML block."""
    cards_html = ""
    for domain in DOMAIN_ORDER:
        avg_pct = _domain_avg_pct(domain, df)
        rating_label, rating_color, _ = get_rating(avg_pct)
        tint_bg = _hex_to_rgba(rating_color, 0.05)
        card_style = (
            f"flex:1;min-width:0;"
            f"background:{tint_bg};"
            f"border:1px solid #30363D;"
            f"border-left:4px solid {rating_color};"
            f"border-radius:12px;padding:14px 13px;height:180px;"
            f"box-sizing:border-box;display:flex;flex-direction:column;overflow:hidden;"
        )
        inner = _card_html(domain, df, avg_pct, rating_label, rating_color)
        cards_html += f"<div style='{card_style}'>{inner}</div>"
    return (
        f"<div style='display:flex;gap:12px;width:100%;margin-bottom:28px;'>"
        f"{cards_html}"
        f"</div>"
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
    st.markdown(_domain_cards_row(df), unsafe_allow_html=True)

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

    # ── Data Sources expander ────────────────────────────────────────────────
    _SOURCE_URL_MAP = {
        "Statistics Canada Labour Force Survey":  "https://www150.statcan.gc.ca/t1/tbl1/en/tv.action?pid=1410038001",
        "CMHC Rental Market Report":              "https://www.cmhc-schl.gc.ca/professionals/housing-markets-data-and-research/market-reports/rental-market-reports-major-centres",
        "Grand River Transit Performance Report": "https://www.grt.ca/en/about-grt/performance-measures.aspx",
        "Ontario Data Catalogue — Housing Supply":"https://data.ontario.ca/dataset/ontario-s-housing-supply-progress",
        "Ontario.ca Long-Term Care":              "https://www.ontario.ca/locations/longtermcare/search/?n=Waterloo%2C+ON",
        "Climate Action Waterloo Region":         "https://dashboard.climateactionwr.ca/",
        "Statistics Canada Crime Severity Index": "https://www150.statcan.gc.ca/t1/tbl1/en/tv.action?pid=3510019101",
    }

    latest_ts = display["Last Updated"].dropna()
    as_of = str(latest_ts.max())[:16] if not latest_ts.empty else "unknown"

    source_rows: list[tuple[str, str, str]] = []
    if "source_name" in df.columns:
        for _, row in df.iterrows():
            sn = str(row.get("source_name") or "").strip()
            domain_str = str(row.get("domain") or "").title()
            ts_str = str(row.get("timestamp") or "")[:10]
            if sn and sn not in {r[0] for r in source_rows}:
                source_rows.append((sn, domain_str, ts_str))

    if source_rows:
        with st.expander(
            f"📚 Data Sources — {len(source_rows)} sources, updated as of {as_of}",
            expanded=False,
        ):
            st.markdown(
                "This scorecard draws from the following data sources. "
                "Fallback data is retrieved via [Tavily AI web search](https://tavily.com) "
                "when primary sources are unavailable.",
            )
            rows_md = "| Source | Domain | Last Fetched | Link |\n|---|---|---|---|\n"
            for sn, dom, ts in sorted(source_rows):
                url = _SOURCE_URL_MAP.get(sn, "")
                link = f"[↗]({url})" if url else "—"
                rows_md += f"| {sn} | {dom} | {ts} | {link} |\n"
            st.markdown(rows_md)
