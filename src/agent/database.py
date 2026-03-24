"""SQLite persistence for scorecard metrics (used by the agent and pipeline)."""

from __future__ import annotations

import logging
import sqlite3
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)

_PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent
DEFAULT_DB_PATH = _PROJECT_ROOT / "data" / "scorecard.db"


def _utc_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def init_db(db_path: str | Path | None = None) -> None:
    """
    Create ``data/scorecard.db`` (and parent dirs) with the ``metrics`` table if missing.
    """
    path = Path(db_path) if db_path else DEFAULT_DB_PATH
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        conn = sqlite3.connect(path)
        try:
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS metrics (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    metric_id TEXT NOT NULL,
                    domain TEXT NOT NULL DEFAULT '',
                    label TEXT,
                    value REAL NOT NULL,
                    unit TEXT,
                    year INTEGER,
                    month INTEGER,
                    source_status TEXT,
                    source_name TEXT DEFAULT '',
                    flagged INTEGER NOT NULL DEFAULT 0,
                    in_human_review INTEGER NOT NULL DEFAULT 0,
                    timestamp TEXT NOT NULL
                )
                """
            )
            # Migration: add source_name to tables created before this column existed
            try:
                conn.execute("ALTER TABLE metrics ADD COLUMN source_name TEXT DEFAULT ''")
            except Exception:
                pass  # Column already exists
            conn.execute(
                "CREATE INDEX IF NOT EXISTS idx_metrics_metric_id_ts ON metrics (metric_id, timestamp DESC)"
            )
            conn.execute(
                "CREATE INDEX IF NOT EXISTS idx_metrics_domain ON metrics (domain)"
            )
            conn.execute(
                "CREATE INDEX IF NOT EXISTS idx_metrics_human_review ON metrics (in_human_review, timestamp DESC)"
            )
            conn.commit()
        finally:
            conn.close()
    except Exception as e:
        logger.exception("init_db failed: %s", e)
        raise


def insert_result(result: dict[str, Any], db_path: str | Path | None = None) -> None:
    """Append one pipeline result row to ``metrics``."""
    path = Path(db_path) if db_path else DEFAULT_DB_PATH
    try:
        ts = result.get("timestamp") or _utc_now_iso()
        flagged = 1 if result.get("flagged") in (True, 1, "1") else 0
        in_review = 1 if result.get("in_human_review") in (True, 1, "1") else 0
        row = (
            str(result["metric_id"]),
            str(result.get("domain", "")),
            result.get("label"),
            float(result["value"]),
            result.get("unit"),
            result.get("year"),
            result.get("month"),
            str(result.get("source_status", "")),
            str(result.get("source_name") or ""),
            flagged,
            in_review,
            str(ts),
        )
        conn = sqlite3.connect(path)
        try:
            conn.execute(
                """
                INSERT INTO metrics (
                    metric_id, domain, label, value, unit, year, month,
                    source_status, source_name, flagged, in_human_review, timestamp
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                row,
            )
            conn.commit()
        finally:
            conn.close()
    except Exception as e:
        logger.exception("insert_result failed: %s", e)
        raise


def get_latest(metric_id: str, db_path: str | Path | None = None) -> dict[str, Any] | None:
    """Return the most recent row for ``metric_id``, or ``None`` if missing / on error."""
    path = Path(db_path) if db_path else DEFAULT_DB_PATH
    try:
        conn = sqlite3.connect(path)
        try:
            conn.row_factory = sqlite3.Row
            cur = conn.execute(
                """
                SELECT metric_id, domain, label, value, unit, year, month,
                       source_status, COALESCE(source_name,'') AS source_name,
                       flagged, in_human_review, timestamp
                FROM metrics
                WHERE metric_id = ?
                ORDER BY timestamp DESC
                LIMIT 1
                """,
                (metric_id,),
            )
            row = cur.fetchone()
            if row is None:
                return None
            return dict(row)
        finally:
            conn.close()
    except Exception as e:
        logger.exception("get_latest failed for %s: %s", metric_id, e)
        return None


def get_history(
    metric_id: str,
    limit: int,
    db_path: str | Path | None = None,
) -> list[dict[str, Any]]:
    """Return up to ``limit`` most recent rows for ``metric_id`` (newest first)."""
    path = Path(db_path) if db_path else DEFAULT_DB_PATH
    try:
        conn = sqlite3.connect(path)
        try:
            conn.row_factory = sqlite3.Row
            cur = conn.execute(
                """
                SELECT metric_id, domain, label, value, unit, year, month,
                       source_status, COALESCE(source_name,'') AS source_name,
                       flagged, in_human_review, timestamp
                FROM metrics
                WHERE metric_id = ?
                ORDER BY timestamp DESC
                LIMIT ?
                """,
                (metric_id, max(1, int(limit))),
            )
            return [dict(r) for r in cur.fetchall()]
        finally:
            conn.close()
    except Exception as e:
        logger.exception("get_history failed for %s: %s", metric_id, e)
        return []
