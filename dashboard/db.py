from __future__ import annotations

import sqlite3
from pathlib import Path

import pandas as pd
import streamlit as st

DB_PATH = Path(__file__).resolve().parent.parent / "data" / "scorecard.db"
METRIC_COLUMNS = [
    "metric_id",
    "domain",
    "label",
    "value",
    "unit",
    "year",
    "month",
    "source_status",
    "flagged",
    "timestamp",
]


def _connect() -> sqlite3.Connection:
    return sqlite3.connect(DB_PATH)


@st.cache_data(show_spinner=False)
def get_all_metrics() -> pd.DataFrame:
    """Return latest row for every metric_id as a DataFrame."""
    query = """
    WITH ranked AS (
        SELECT metric_id, domain, label, value, unit, year, month, source_status, flagged, timestamp,
               ROW_NUMBER() OVER (PARTITION BY metric_id ORDER BY timestamp DESC) AS rn
        FROM metrics
    )
    SELECT metric_id, domain, label, value, unit, year, month, source_status, flagged, timestamp
    FROM ranked
    WHERE rn = 1
    ORDER BY domain, metric_id
    """
    try:
        with _connect() as conn:
            return pd.read_sql_query(query, conn)
    except Exception:
        return pd.DataFrame(columns=METRIC_COLUMNS)


@st.cache_data(show_spinner=False)
def get_metric_history(metric_id: str) -> pd.DataFrame:
    """Return one averaged row per (year, month) for a metric, ordered chronologically.

    Averaging across all rows for the same period removes noise from multiple
    pipeline runs writing slightly different values in the same month.
    """
    query = """
    SELECT
        metric_id,
        domain,
        label,
        AVG(value)      AS value,
        unit,
        year,
        month,
        source_status,
        flagged,
        MAX(timestamp)  AS timestamp
    FROM metrics
    WHERE metric_id = ?
    GROUP BY metric_id, domain, label, unit, year, COALESCE(month, 0), source_status, flagged
    ORDER BY year ASC, COALESCE(month, 0) ASC
    """
    try:
        with _connect() as conn:
            return pd.read_sql_query(query, conn, params=[metric_id])
    except Exception:
        return pd.DataFrame(columns=METRIC_COLUMNS)


@st.cache_data(show_spinner=False)
def get_domain_summary(domain: str) -> pd.DataFrame:
    """Return latest metric rows for one domain."""
    all_df = get_all_metrics()
    if all_df.empty:
        return all_df
    return all_df[all_df["domain"].str.lower() == domain.lower()].copy()


@st.cache_data(show_spinner=False)
def get_system_health() -> pd.DataFrame:
    """Return last update and status for every metric."""
    all_df = get_all_metrics()
    if all_df.empty:
        return pd.DataFrame(columns=["metric_id", "label", "source_status", "last_updated", "domain"])
    health = all_df[["metric_id", "label", "source_status", "timestamp", "domain"]].copy()
    health = health.rename(columns={"timestamp": "last_updated"})
    return health.sort_values(["source_status", "last_updated", "metric_id"], ascending=[True, False, True])
