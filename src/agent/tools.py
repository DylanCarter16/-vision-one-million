"""LangChain tools for querying the local scorecard SQLite database."""

from __future__ import annotations

import json
import logging
from pathlib import Path
from typing import Any

from langchain.tools import tool

from .database import DEFAULT_DB_PATH, get_latest

logger = logging.getLogger(__name__)


def build_scorecard_tools(db_path: str | Path | None = None) -> list[Any]:
    """
    Construct tool callables bound to ``db_path`` (defaults to ``data/scorecard.db``).
    """
    path = str(Path(db_path) if db_path else DEFAULT_DB_PATH)

    @tool
    def query_metrics(metric_id: str) -> str:
        """
        Look up a single scorecard metric by its stable identifier (metric_id).

        Use this when the user asks for the current or latest value of a specific metric,
        or when you need the timestamp of the most recent observation.

        Returns JSON with: metric_id, domain, label, value, unit, year, month,
        source_status, flagged, in_human_review, timestamp — or an error if not found.
        """
        try:
            row = get_latest(metric_id, db_path=path)
            if row is None:
                return json.dumps(
                    {
                        "error": "not_found",
                        "metric_id": metric_id,
                        "detail": "No rows for this metric_id in the database.",
                    }
                )
            return json.dumps(dict(row), default=str)
        except Exception as e:
            logger.exception("query_metrics failed: %s", e)
            return json.dumps({"error": str(e), "metric_id": metric_id})

    @tool
    def compare_metrics(metric_id_a: str, metric_id_b: str) -> str:
        """
        Compare the latest stored values for two different metrics (two metric_ids).

        Use when the user wants a percent difference or ratio between two indicators
        (e.g. housing vs employment). Computes percent change from metric A's latest
        value to metric B's latest value: (B - A) / A * 100. If A is zero, returns an error.

        Arguments: metric_id_a — baseline metric id; metric_id_b — comparison metric id.
        """
        try:
            a = get_latest(metric_id_a, db_path=path)
            b = get_latest(metric_id_b, db_path=path)
            if a is None or b is None:
                return json.dumps(
                    {
                        "error": "missing_metric",
                        "metric_id_a": metric_id_a,
                        "metric_id_b": metric_id_b,
                        "found_a": a is not None,
                        "found_b": b is not None,
                    }
                )
            va, vb = float(a["value"]), float(b["value"])
            if va == 0:
                return json.dumps(
                    {
                        "error": "baseline_zero",
                        "message": "Latest value for metric_id_a is zero; percent change undefined.",
                        "metric_id_a": metric_id_a,
                        "metric_id_b": metric_id_b,
                        "value_a": va,
                        "value_b": vb,
                    }
                )
            pct = (vb - va) / va * 100.0
            return json.dumps(
                {
                    "metric_id_a": metric_id_a,
                    "metric_id_b": metric_id_b,
                    "latest_value_a": va,
                    "latest_value_b": vb,
                    "timestamp_a": a.get("timestamp"),
                    "timestamp_b": b.get("timestamp"),
                    "percent_change_a_to_b": round(pct, 4),
                    "interpretation": "Percent change from A's latest value to B's latest value.",
                }
            )
        except Exception as e:
            logger.exception("compare_metrics failed: %s", e)
            return json.dumps({"error": str(e)})

    @tool
    def list_domain_metrics(domain: str) -> str:
        """
        List every metric_id in a given subject area (domain) with its latest value.

        Use when the user asks for all housing metrics, all healthcare metrics, etc.
        Domains are stored on each row (e.g. 'housing', 'transportation', 'healthcare', 'employment').
        Matching is case-insensitive.

        Returns JSON: list of {metric_id, label, value, unit, year, month, timestamp, source_status}.
        """
        try:
            import sqlite3

            conn = sqlite3.connect(path)
            try:
                conn.row_factory = sqlite3.Row
                cur = conn.execute(
                    """
                    WITH ranked AS (
                        SELECT metric_id, domain, label, value, unit, year, month,
                               source_status, flagged, in_human_review, timestamp,
                               ROW_NUMBER() OVER (
                                   PARTITION BY metric_id ORDER BY timestamp DESC
                               ) AS rn
                        FROM metrics
                        WHERE lower(domain) = lower(?)
                    )
                    SELECT metric_id, domain, label, value, unit, year, month,
                           source_status, flagged, in_human_review, timestamp
                    FROM ranked
                    WHERE rn = 1
                    ORDER BY metric_id
                    """,
                    (domain.strip(),),
                )
                rows = [dict(r) for r in cur.fetchall()]
                return json.dumps({"domain": domain, "count": len(rows), "metrics": rows})
            finally:
                conn.close()
        except Exception as e:
            logger.exception("list_domain_metrics failed: %s", e)
            return json.dumps({"error": str(e), "domain": domain})

    @tool
    def get_flagged_metrics() -> str:
        """
        Return metrics that are in the human review queue (awaiting analyst sign-off).

        Use when the user asks what needs human review, what is flagged for QA,
        or what is blocked in the workflow. Rows have in_human_review = 1 in the database.

        Returns JSON with a list of the latest queue row per metric_id.
        """
        try:
            import sqlite3

            conn = sqlite3.connect(path)
            try:
                conn.row_factory = sqlite3.Row
                cur = conn.execute(
                    """
                    WITH ranked AS (
                        SELECT metric_id, domain, label, value, unit, year, month,
                               source_status, flagged, in_human_review, timestamp,
                               ROW_NUMBER() OVER (
                                   PARTITION BY metric_id ORDER BY timestamp DESC
                               ) AS rn
                        FROM metrics
                        WHERE in_human_review = 1
                    )
                    SELECT metric_id, domain, label, value, unit, year, month,
                           source_status, flagged, in_human_review, timestamp
                    FROM ranked
                    WHERE rn = 1
                    ORDER BY timestamp DESC
                    """
                )
                rows = [dict(r) for r in cur.fetchall()]
                return json.dumps({"count": len(rows), "human_review_queue": rows})
            finally:
                conn.close()
        except Exception as e:
            logger.exception("get_flagged_metrics failed: %s", e)
            return json.dumps({"error": str(e)})

    return [query_metrics, compare_metrics, list_domain_metrics, get_flagged_metrics]
