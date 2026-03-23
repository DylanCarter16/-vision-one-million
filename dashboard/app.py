from __future__ import annotations

import random
import sqlite3
import sys
from datetime import datetime, timezone
from pathlib import Path

import streamlit as st

# ---------------------------------------------------------------------------
# Ensure src/ and dashboard/ are importable on Streamlit Cloud.
# ---------------------------------------------------------------------------
_ROOT = Path(__file__).resolve().parent.parent
_SRC = _ROOT / "src"
_DASH = Path(__file__).resolve().parent
for _p in (_SRC, _DASH):
    if str(_p) not in sys.path:
        sys.path.insert(0, str(_p))

from agent.database import init_db, insert_result  # noqa: E402

from db import get_all_metrics, get_domain_summary  # noqa: E402
from pages import domain_detail, overview, system_health  # noqa: E402
from scorecard_data import SCORECARD_METRICS  # noqa: E402

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------
ACCENT = "#00C853"
WARN = "#FFB300"
DANGER = "#FF5252"
CARD_BG = "#1E2329"
BG = "#0D1117"

DOMAIN_PAGES = ["Housing", "Transportation", "Healthcare", "Employment", "Placemaking"]

_DB_PATH = _ROOT / "data" / "scorecard.db"

# ---------------------------------------------------------------------------
# Startup seeding — auto-populate if the DB is missing or empty.
# Build seed specs directly from the canonical SCORECARD_METRICS catalogue
# so there is a single source of truth.
# ---------------------------------------------------------------------------
def _build_seed_specs() -> list[dict]:
    specs = []
    for m in SCORECARD_METRICS:
        low = m.current * 0.88
        high = m.current * 1.12
        specs.append(
            {
                "metric_id": m.metric_id,
                "domain": m.domain,
                "label": m.label,
                "unit": m.unit,
                "low": low,
                "high": high,
                "jitter": m.jitter if m.jitter > 0 else abs(m.current) * 0.02 + 0.001,
                "integer": m.integer,
            }
        )
    return specs


def _db_has_rows() -> bool:
    try:
        _DB_PATH.parent.mkdir(parents=True, exist_ok=True)
        conn = sqlite3.connect(_DB_PATH)
        try:
            cur = conn.execute(
                "SELECT COUNT(*) FROM sqlite_master WHERE type='table' AND name='metrics'"
            )
            if cur.fetchone()[0] == 0:
                return False
            return bool(conn.execute("SELECT 1 FROM metrics LIMIT 1").fetchone())
        finally:
            conn.close()
    except Exception:
        return False


def seed_if_empty() -> None:
    """Insert 12 months of sample data for all scorecard metrics if the database is empty."""
    if _db_has_rows():
        return
    init_db(_DB_PATH)
    rng = random.Random(42)
    year = 2024
    seed_specs = _build_seed_specs()
    for month in range(1, 13):
        ts = datetime(year, month, 15, 14, 0, 0, tzinfo=timezone.utc).isoformat()
        seasonal = 0.5 * (month - 6.5) / 6.0
        for spec in seed_specs:
            base = rng.uniform(spec["low"], spec["high"])
            noise = rng.gauss(0, spec["jitter"])
            raw = base + noise + seasonal * (spec["high"] - spec["low"]) * 0.03
            raw = max(spec["low"] * 0.95, min(spec["high"] * 1.05, raw))
            value = float(round(raw) if spec["integer"] else round(raw, 2))
            insert_result(
                {
                    "metric_id": spec["metric_id"],
                    "domain": spec["domain"],
                    "label": spec["label"],
                    "value": value,
                    "unit": spec["unit"],
                    "year": year,
                    "month": month,
                    "source_status": "success",
                    "flagged": 0,
                    "in_human_review": 0,
                    "timestamp": ts,
                },
                db_path=_DB_PATH,
            )


# ---------------------------------------------------------------------------
# Theme
# ---------------------------------------------------------------------------
_THEME_CSS = f"""
<style>
/* ── base ── */
html, body, [data-testid="stAppViewContainer"], .stApp {{
    background-color: {BG} !important;
    color: #E6EDF3 !important;
    font-family: 'Inter', 'Segoe UI', sans-serif;
}}

/* ── sidebar ── */
[data-testid="stSidebar"] {{
    background-color: #161B22 !important;
    border-right: 1px solid #30363D;
}}
[data-testid="stSidebar"] * {{ color: #E6EDF3 !important; }}

/* ── metric cards ── */
[data-testid="stMetric"] {{
    background: {CARD_BG};
    border: 1px solid #30363D;
    border-radius: 12px;
    padding: 16px 20px;
}}
[data-testid="stMetricLabel"] {{ color: #8B949E !important; font-size: 0.78rem; text-transform: uppercase; letter-spacing: 0.06em; }}
[data-testid="stMetricValue"] {{ color: #E6EDF3 !important; font-size: 1.9rem !important; font-weight: 700; }}

/* ── dataframe ── */
[data-testid="stDataFrame"] {{ border-radius: 8px; overflow: hidden; }}
thead tr th {{ background-color: #161B22 !important; color: #8B949E !important; font-size: 0.75rem; text-transform: uppercase; letter-spacing: 0.05em; }}
tbody tr:nth-child(even) {{ background-color: #161B22; }}
tbody tr:hover {{ background-color: #21262D; }}

/* ── badges ── */
.badge {{
    display: inline-block;
    padding: 2px 10px;
    border-radius: 12px;
    font-size: 0.72rem;
    font-weight: 600;
    letter-spacing: 0.04em;
    text-transform: uppercase;
}}
.badge-success {{ background: #0d2818; color: {ACCENT}; border: 1px solid {ACCENT}44; }}
.badge-fallback {{ background: #2d1e02; color: {WARN}; border: 1px solid {WARN}44; }}
.badge-failed   {{ background: #2d0a0a; color: {DANGER}; border: 1px solid {DANGER}44; }}

/* ── section headers ── */
h2, h3 {{ color: #E6EDF3 !important; font-weight: 700; }}

/* ── buttons ── */
.stButton > button {{
    background: {ACCENT} !important;
    color: #000 !important;
    border: none !important;
    border-radius: 8px !important;
    font-weight: 700 !important;
}}
.stButton > button:hover {{ opacity: 0.88; }}
</style>
"""


def _inject_theme() -> None:
    st.markdown(_THEME_CSS, unsafe_allow_html=True)


# ---------------------------------------------------------------------------
# Sidebar helpers
# ---------------------------------------------------------------------------
def _status_badge(status: str) -> str:
    s = (status or "").lower()
    cls = "badge-success" if s == "success" else ("badge-fallback" if s == "fallback" else "badge-failed")
    return f'<span class="badge {cls}">{s or "unknown"}</span>'


def _domain_status(domain: str) -> str:
    df = get_domain_summary(domain)
    if df.empty:
        return "failed"
    statuses = df["source_status"].astype(str).str.lower()
    if (statuses == "success").all():
        return "success"
    if (statuses == "failed").all():
        return "failed"
    return "fallback"


def _sidebar_status() -> str:
    lines = ["<p style='font-size:0.72rem;text-transform:uppercase;letter-spacing:0.08em;color:#8B949E;margin-bottom:8px;'>Domain Status</p>"]
    for domain in [d.lower() for d in DOMAIN_PAGES]:
        s = _domain_status(domain)
        lines.append(f"<div style='margin-bottom:6px;'>{_status_badge(s)} <span style='font-size:0.9rem;color:#E6EDF3;'>{domain.title()}</span></div>")
    return "".join(lines)


def _last_updated_text() -> str:
    df = get_all_metrics()
    if df.empty or "timestamp" not in df.columns:
        return "No updates yet"
    ts = df["timestamp"].dropna().astype(str)
    return str(ts.max())[:16].replace("T", " ") if not ts.empty else "No updates yet"


# ---------------------------------------------------------------------------
# App shell
# ---------------------------------------------------------------------------
def main() -> None:
    seed_if_empty()
    st.set_page_config(
        page_title="Vision One Million | Waterloo Region",
        page_icon="🏙️",
        layout="wide",
        initial_sidebar_state="expanded",
    )
    _inject_theme()

    with st.sidebar:
        st.markdown(
            f"<h2 style='font-size:1.1rem;font-weight:800;color:#E6EDF3;margin-bottom:2px;'>🏙️ Vision One Million</h2>"
            f"<p style='font-size:0.75rem;color:#8B949E;margin-bottom:20px;'>Waterloo Region Scorecard</p>",
            unsafe_allow_html=True,
        )
        page = st.radio(
            "Navigate",
            ["Overview", *DOMAIN_PAGES, "System Health"],
            index=0,
            label_visibility="collapsed",
        )
        st.markdown("<hr style='border:none;border-top:1px solid #00C853;margin:16px 0;opacity:0.45;'>", unsafe_allow_html=True)
        st.markdown(_sidebar_status(), unsafe_allow_html=True)
        st.markdown(
            f"<p style='font-size:0.72rem;color:#8B949E;margin-top:20px;'>Last updated<br/><span style='color:#E6EDF3;'>{_last_updated_text()}</span></p>",
            unsafe_allow_html=True,
        )

    if page == "Overview":
        overview.render()
    elif page == "System Health":
        system_health.render()
    else:
        domain_detail.render(page.lower())


if __name__ == "__main__":
    main()
