#!/usr/bin/env python3
"""
Seed data/scorecard.db with 12 months of sample metrics for Waterloo Region.

Run from the project root:
    python scripts/seed_db.py
"""

from __future__ import annotations

import importlib.util
import random
import sys
from datetime import datetime, timezone
from pathlib import Path

# Project root
_ROOT = Path(__file__).resolve().parent.parent

# Make dashboard/ importable so we can use scorecard_data
_DASH = _ROOT / "dashboard"
if str(_DASH) not in sys.path:
    sys.path.insert(0, str(_DASH))

from scorecard_data import SCORECARD_METRICS  # noqa: E402

# Load database module directly to avoid importing the full agent package graph.
_db_mod_path = _ROOT / "src" / "agent" / "database.py"
_spec = importlib.util.spec_from_file_location("agent_database", _db_mod_path)
if _spec is None or _spec.loader is None:
    raise ImportError(f"Cannot load database module from {_db_mod_path}")
_mod = importlib.util.module_from_spec(_spec)
sys.modules["agent_database"] = _mod
_spec.loader.exec_module(_mod)
init_db = _mod.init_db
insert_result = _mod.insert_result

YEAR = 2024


def _month_timestamp(year: int, month: int) -> str:
    return datetime(year, month, 15, 14, 0, 0, tzinfo=timezone.utc).isoformat()


def main() -> None:
    init_db()
    rng = random.Random(42)

    for month in range(1, 13):
        ts = _month_timestamp(YEAR, month)
        seasonal = 0.5 * (month - 6.5) / 6.0

        for m in SCORECARD_METRICS:
            low = m.current * 0.88
            high = m.current * 1.12
            jitter = m.jitter if m.jitter > 0 else abs(m.current) * 0.02 + 0.001
            base = rng.uniform(low, high)
            noise = rng.gauss(0, jitter)
            raw = base + noise + seasonal * (high - low) * 0.03
            raw = max(low * 0.95, min(high * 1.05, raw))
            value = float(round(raw) if m.integer else round(raw, 2))

            insert_result(
                {
                    "metric_id": m.metric_id,
                    "domain": m.domain,
                    "label": m.label,
                    "value": value,
                    "unit": m.unit,
                    "year": YEAR,
                    "month": month,
                    "source_status": "success",
                    "flagged": 0,
                    "in_human_review": 0,
                    "timestamp": ts,
                }
            )

    db_path = _ROOT / "data" / "scorecard.db"
    print(f"Seeded {len(SCORECARD_METRICS)} metrics x 12 months into {db_path}")


if __name__ == "__main__":
    main()
