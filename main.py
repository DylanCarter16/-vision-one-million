"""Pipeline entrypoint: fetch current values from configured sources and persist to SQLite."""

from __future__ import annotations

import logging
import os
import re
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import requests
import yaml
from dotenv import load_dotenv

ROOT = Path(__file__).resolve().parent
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from agent.database import get_latest, init_db, insert_result  # noqa: E402

logger = logging.getLogger("vision_one_million.main")

SOURCES_PATH = ROOT / "config" / "sources.yaml"

EXPECTED_RANGES: dict[str, tuple[float, float]] = {
    "housing_starts_total": (700.0, 1500.0),
    "average_home_price": (550_000.0, 900_000.0),
    "transit_ridership": (1_000_000.0, 2_000_000.0),
    "unemployment_rate": (3.0, 10.0),
    "er_wait_times": (2.5, 8.0),
}


def _load_config() -> dict[str, Any]:
    if not SOURCES_PATH.exists():
        raise FileNotFoundError(f"Missing config file: {SOURCES_PATH}")
    with open(SOURCES_PATH, encoding="utf-8") as f:
        data = yaml.safe_load(f) or {}
    if not (data.get("metrics") or []):
        raise ValueError(f"No metrics configured in {SOURCES_PATH}")
    return data


def _extract_candidates(text: str) -> list[float]:
    matches = re.findall(r"\d[\d,]*(?:\.\d+)?", text)
    out: list[float] = []
    for m in matches:
        try:
            out.append(float(m.replace(",", "")))
        except ValueError:
            continue
    return out


def _pick_value(metric_id: str, text: str) -> float | None:
    lo, hi = EXPECTED_RANGES.get(metric_id, (float("-inf"), float("inf")))
    candidates = _extract_candidates(text)
    in_range = [x for x in candidates if lo <= x <= hi]
    if not in_range:
        return None
    # Prefer smaller plausible rates for percentages / wait hours
    if metric_id in {"unemployment_rate", "er_wait_times"}:
        return round(min(in_range), 2)
    # Otherwise prefer larger values for count/price-like metrics
    value = max(in_range)
    if metric_id in {"housing_starts_total", "transit_ridership"}:
        return float(round(value))
    return round(value, 2)


def _fetch_text(url: str) -> str:
    r = requests.get(url, timeout=30, headers={"User-Agent": "VisionOneMillion/1.0"})
    r.raise_for_status()
    return r.text


def _tavily_text(query: str) -> str:
    api_key = os.environ.get("TAVILY_API_KEY", "")
    if not api_key:
        return ""
    try:
        r = requests.post(
            "https://api.tavily.com/search",
            timeout=30,
            json={"api_key": api_key, "query": query, "max_results": 5},
        )
        r.raise_for_status()
        payload = r.json()
        results = payload.get("results") or []
        return "\n".join((res.get("content") or "") for res in results if isinstance(res, dict))
    except Exception as exc:
        logger.warning("Tavily fallback failed for query=%r: %s", query, exc)
        return ""


def _persist(metric: dict[str, Any], value: float, status: str) -> None:
    now = datetime.now(timezone.utc)
    insert_result(
        {
            "metric_id": metric["metric_id"],
            "domain": metric.get("domain", ""),
            "label": metric.get("label") or metric["metric_id"],
            "value": value,
            "unit": metric.get("unit"),
            "year": now.year,
            "month": now.month,
            "source_status": status,
            "flagged": 0 if status == "success" else 1,
            "in_human_review": 0 if status == "success" else 1,
            "timestamp": now.isoformat(),
        }
    )


def run_pipeline() -> tuple[int, int]:
    load_dotenv()
    init_db()
    cfg = _load_config()
    metrics = cfg.get("metrics") or []

    successes = 0
    total = 0
    for metric in metrics:
        total += 1
        metric_id = str(metric.get("metric_id", "")).strip()
        if not metric_id:
            logger.warning("Skipping metric row without metric_id: %s", metric)
            continue
        url = str(metric.get("source_url", "")).strip()
        value: float | None = None
        status = "failed"
        try:
            text = _fetch_text(url)
            value = _pick_value(metric_id, text)
            if value is not None:
                status = "success"
        except Exception as exc:
            logger.warning("Primary fetch failed for %s (%s): %s", metric_id, url, exc)

        if value is None:
            query = f"{metric.get('label', metric_id)} Waterloo Region latest value"
            fallback_text = _tavily_text(query)
            value = _pick_value(metric_id, fallback_text)
            if value is not None:
                status = "fallback"

        if value is None:
            latest = get_latest(metric_id)
            if latest and latest.get("value") is not None:
                value = float(latest["value"])
                status = "failed"
            else:
                logger.error("No value available for %s from source/fallback/history", metric_id)
                continue

        _persist(metric, value, status)
        if status == "success":
            successes += 1
        logger.info("Stored %s=%s (%s)", metric_id, value, status)

    return successes, total


def main() -> None:
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")
    successes, total = run_pipeline()
    print(f"Pipeline complete: {successes}/{total} metrics fetched via primary source.")


if __name__ == "__main__":
    main()
