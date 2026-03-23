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
import yaml

# Project root: .../vision-one-million
_ROOT = Path(__file__).resolve().parent.parent

# Load database module directly so we do not import the full `agent` package graph.
_db_mod_path = _ROOT / "src" / "agent" / "database.py"
_spec = importlib.util.spec_from_file_location("agent_database", _db_mod_path)
if _spec is None or _spec.loader is None:
    raise ImportError(f"Cannot load database module from {_db_mod_path}")
_mod = importlib.util.module_from_spec(_spec)
sys.modules["agent_database"] = _mod
_spec.loader.exec_module(_mod)
init_db = _mod.init_db
insert_result = _mod.insert_result

REGION = "Waterloo Region"
YEAR = 2024  # 12 calendar months
SOURCES_PATH = _ROOT / "config" / "sources.yaml"


def _month_timestamp(year: int, month: int) -> str:
    """ISO timestamp typical of a mid-month stats release (UTC)."""
    # 15th ~14:00 UTC — plausible publication time after month close
    return datetime(year, month, 15, 14, 0, 0, tzinfo=timezone.utc).isoformat()


def main() -> None:
    init_db()
    rng = random.Random(42)

    with open(SOURCES_PATH, encoding="utf-8") as f:
        cfg = yaml.safe_load(f) or {}
    yaml_metrics = cfg.get("metrics") or []
    if not yaml_metrics:
        raise ValueError(f"No metrics found in {SOURCES_PATH}")

    seed_specs = {
        "housing_starts_total": {"low": 800, "high": 1200, "jitter": 40.0},
        "average_home_price": {"low": 650_000, "high": 750_000, "jitter": 3_000.0},
        "transit_ridership": {"low": 1_200_000, "high": 1_800_000, "jitter": 50_000.0},
        "unemployment_rate": {"low": 4.5, "high": 6.5, "jitter": 0.15},
        "er_wait_times": {"low": 3.5, "high": 6.5, "jitter": 0.2},
    }
    int_metrics = {"housing_starts_total", "transit_ridership"}

    metrics: list[dict] = []
    for row in yaml_metrics:
        metric_id = str(row.get("metric_id", "")).strip()
        if not metric_id:
            continue
        if metric_id not in seed_specs:
            raise ValueError(f"Missing seed range for metric_id={metric_id!r}")
        spec = seed_specs[metric_id]
        metrics.append(
            {
                "metric_id": metric_id,
                "domain": str(row.get("domain", "")),
                "label": str(row.get("label", metric_id)),
                "unit": str(row.get("unit", "")),
                **spec,
            }
        )

    for month in range(1, 13):
        ts = _month_timestamp(YEAR, month)
        # Slight seasonal / drift so series are not flat
        seasonal = 0.5 * (month - 6.5) / 6.0

        for spec in metrics:
            base = rng.uniform(spec["low"], spec["high"])
            noise = rng.gauss(0, spec["jitter"])
            value = base + noise + seasonal * (spec["high"] - spec["low"]) * 0.03
            value = max(spec["low"] * 0.95, min(spec["high"] * 1.05, value))
            if spec["metric_id"] in int_metrics:
                value = round(value)
            else:
                value = round(value, 2)

            insert_result(
                {
                    "metric_id": spec["metric_id"],
                    "domain": spec["domain"],
                    "label": spec["label"],
                    "value": float(value),
                    "unit": spec["unit"],
                    "year": YEAR,
                    "month": month,
                    "source_status": "success",
                    "flagged": 0,
                    "in_human_review": 0,
                    "timestamp": ts,
                }
            )

    print(f"Seeded {len(metrics)} metrics x 12 months into {_ROOT / 'data' / 'scorecard.db'}")


if __name__ == "__main__":
    main()
