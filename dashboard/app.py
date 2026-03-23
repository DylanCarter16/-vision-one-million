from __future__ import annotations

import random
import sqlite3
import sys
from datetime import datetime, timezone
from pathlib import Path

import streamlit as st

# ---------------------------------------------------------------------------
# Ensure src/ is on the path so agent.database is importable on Streamlit Cloud
# (no editable install available there).
# ---------------------------------------------------------------------------
_ROOT = Path(__file__).resolve().parent.parent
_SRC = _ROOT / "src"
if str(_SRC) not in sys.path:
    sys.path.insert(0, str(_SRC))

from agent.database import init_db, insert_result  # noqa: E402

from db import get_all_metrics, get_domain_summary
from pages import domain_detail, overview, system_health


# ---------------------------------------------------------------------------
# Startup seeding: auto-populate if the DB is missing or empty.
# ---------------------------------------------------------------------------

_DB_PATH = _ROOT / "data" / "scorecard.db"

_SEED_SPECS: list[dict] = [
    {
        "metric_id": "housing_starts_total",
        "domain": "housing",
        "label": "Housing starts (Waterloo Region)",
        "unit": "units",
        "low": 800.0,
        "high": 1200.0,
        "jitter": 40.0,
        "integer": True,
    },
    {
        "metric_id": "average_home_price",
        "domain": "housing",
        "label": "Average home price (Waterloo Region)",
        "unit": "CAD",
        "low": 650_000.0,
        "high": 750_000.0,
        "jitter": 3_000.0,
        "integer": False,
    },
    {
        "metric_id": "transit_ridership",
        "domain": "transportation",
        "label": "Transit ridership (Grand River Transit)",
        "unit": "trips/month",
        "low": 1_200_000.0,
        "high": 1_800_000.0,
        "jitter": 50_000.0,
        "integer": True,
    },
    {
        "metric_id": "unemployment_rate",
        "domain": "employment",
        "label": "Unemployment rate (Waterloo Region)",
        "unit": "%",
        "low": 4.5,
        "high": 6.5,
        "jitter": 0.15,
        "integer": False,
    },
    {
        "metric_id": "er_wait_times",
        "domain": "healthcare",
        "label": "ER wait time — 90th percentile (Waterloo Region)",
        "unit": "hours",
        "low": 3.5,
        "high": 6.5,
        "jitter": 0.2,
        "integer": False,
    },
]


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
    """Insert 12 months of sample data for Waterloo Region if the database is empty."""
    if _db_has_rows():
        return

    init_db(_DB_PATH)
    rng = random.Random(42)
    year = 2024

    for month in range(1, 13):
        ts = datetime(year, month, 15, 14, 0, 0, tzinfo=timezone.utc).isoformat()
        seasonal = 0.5 * (month - 6.5) / 6.0

        for spec in _SEED_SPECS:
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
    seed_if_empty()
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