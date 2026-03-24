"""
Employment fetcher — StatCan Web Data Service + Tavily fallback.

Statistics Canada WDS API (no key required):
  Base: https://www150.statcan.gc.ca/t1/tbl1/en/dtbl/
  Table 14-10-0380-01: Labour force characteristics by CMA
  KCW CMA code 541 corresponds to coordinate member 48 in the geography axis.

The coordinate string format for the WDS is:
  <table_pid>/<dim1>.<dim2>...<dimN>
For 14-10-0380-01 the axes are:
  1 Geography, 2 Labour force characteristics, 3 Sex, 4 Age group,
  5 Data type, 6 Seasonal adjustment, 7 UOM, 8 SCALAR_FACTOR
We use:
  Geography = 48  (Kitchener-Cambridge-Waterloo)
  Characteristic = 3  (Unemployment rate) | 2  (Employment rate)
  Sex = 1  (Both sexes)
  Age = 1  (15 years and over)
  Data type = 1, Seasonal adj = 2 (seasonally adjusted)
  UOM = 1, SCALAR = 1
"""

from __future__ import annotations

import logging
import os
import re
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import requests
from dotenv import load_dotenv

_SRC = Path(__file__).resolve().parents[3]
if str(_SRC) not in sys.path:
    sys.path.insert(0, str(_SRC))

from agent.database import insert_result  # noqa: E402

load_dotenv()
logger = logging.getLogger(__name__)

# StatCan WDS base
_WDS = "https://www150.statcan.gc.ca/t1/tbl1/en/dtbl"
_TABLE = "1410038001"
_HEADERS = {"User-Agent": "VisionOneMillion/1.0 (+https://github.com/DylanCarter16/-vision-one-million)"}
_TIMEOUT = 20


# Coordinate helper: Geography=48 (KCW), Char=?, Sex=1, Age=1, DataType=1, SeasonAdj=2, UOM=1, Scalar=1
def _coord(char_member: int) -> str:
    return f"48.{char_member}.1.1.1.2.1.1"


def _wds_latest(coord: str, n_periods: int = 1) -> list[dict[str, Any]]:
    url = f"{_WDS}/getDataFromCubePidCoordAndLatestNPeriods/{_TABLE}/{coord}/{n_periods}"
    resp = requests.get(url, headers=_HEADERS, timeout=_TIMEOUT)
    resp.raise_for_status()
    body = resp.json()
    # WDS returns a list; each item has "object" with "vectorDataPoint"
    if isinstance(body, list) and body:
        points = body[0].get("object", {}).get("vectorDataPoint", [])
        return points if isinstance(points, list) else []
    return []


def _extract_float(points: list[dict[str, Any]]) -> float | None:
    for pt in points:
        raw = pt.get("value")
        if raw is not None:
            try:
                return float(raw)
            except (TypeError, ValueError):
                continue
    return None


def _tavily_search(query: str, lo: float, hi: float) -> float | None:
    """Search Tavily and return the first number in [lo, hi], or None."""
    api_key = os.environ.get("TAVILY_API_KEY", "")
    if not api_key:
        logger.warning("TAVILY_API_KEY not set; skipping Tavily fallback")
        return None
    try:
        from tavily import TavilyClient
        client = TavilyClient(api_key=api_key)
        resp = client.search(query=query, max_results=5)
        text = " ".join(
            (r.get("content") or "") for r in (resp.get("results") or [])
        )
        candidates = []
        for m in re.findall(r"\d+(?:\.\d+)?", text):
            try:
                v = float(m.replace(",", ""))
                if lo <= v <= hi:
                    candidates.append(v)
            except ValueError:
                continue
        return candidates[0] if candidates else None
    except Exception as exc:
        logger.warning("Tavily search failed: %s", exc)
        return None


_SRC_STATCAN = "Statistics Canada Labour Force Survey"
_SRC_TAVILY  = "Tavily Web Search"


def _store(
    metric_id: str,
    domain: str,
    label: str,
    value: float,
    unit: str,
    status: str,
    now: datetime,
    source_name: str = "",
) -> None:
    insert_result(
        {
            "metric_id": metric_id,
            "domain": domain,
            "label": label,
            "value": value,
            "unit": unit,
            "year": now.year,
            "month": now.month,
            "source_status": status,
            "source_name": source_name,
            "flagged": 0,
            "in_human_review": 0,
            "timestamp": now.isoformat(),
        }
    )


class EmploymentFetcher:
    """Fetches real employment metrics for Kitchener-Cambridge-Waterloo from StatCan."""

    DOMAIN = "employment"

    def fetch_unemployment_rate(self) -> tuple[float | None, str]:
        """
        Priority 1: StatCan WDS API for KCW CMA unemployment rate.
        Priority 3: Tavily hyper-specific query.
        Returns (value %, source_key).
        """
        # ── Priority 1: StatCan WDS ──────────────────────────────────────────
        try:
            points = _wds_latest(_coord(3))  # char 3 = Unemployment rate
            value = _extract_float(points)
            if value is not None and 0.5 <= value <= 20.0:
                print(f"    ✓ Priority 1 (StatCan API): unemployment_rate = {value:.1f}%")
                logger.info("StatCan unemployment rate for KCW: %.1f%%", value)
                return value, "statcan"
            logger.warning("StatCan unemployment rate out of expected range or empty")
            print("    ✗ Priority 1 (StatCan): no valid unemployment rate in response")
        except Exception as exc:
            logger.warning("StatCan API failed for unemployment_rate: %s", exc)
            print(f"    ✗ Priority 1 (StatCan): {exc}")

        # ── Priority 3: Tavily ───────────────────────────────────────────────
        print("    → Priority 3 (Tavily)…")
        value = _tavily_search(
            "Kitchener-Cambridge-Waterloo CMA unemployment rate 2026 "
            "Statistics Canada Labour Force Survey percent",
            lo=2.0, hi=15.0,
        )
        if value is not None:
            print(f"    ✓ Priority 3 (Tavily): unemployment_rate = {value:.1f}%")
        return value, "tavily"

    def fetch_employment_rate(self) -> tuple[float | None, str]:
        """
        Compute % of labour force employed as (100 - unemployment_rate).
        target=96 means 4% unemployment (96% employed).
        Priority 1: StatCan; Priority 3: Tavily.
        """
        # ── Priority 1: StatCan WDS — derive from unemployment rate ──────────
        try:
            points = _wds_latest(_coord(3))  # char 3 = Unemployment rate
            unemp = _extract_float(points)
            if unemp is not None and 0.5 <= unemp <= 20.0:
                employed = round(100.0 - unemp, 1)
                print(f"    ✓ Priority 1 (StatCan API): regional_employment = {employed:.1f}% "
                      f"(unemployment {unemp:.1f}%)")
                logger.info("Regional employment derived: %.1f%%", employed)
                return employed, "statcan"
            logger.warning("StatCan unemployment data missing/out-of-range for employment calc")
            print("    ✗ Priority 1 (StatCan): could not derive employment rate")
        except Exception as exc:
            logger.warning("StatCan API failed for regional_employment: %s", exc)
            print(f"    ✗ Priority 1 (StatCan): {exc}")

        # ── Priority 3: Tavily ───────────────────────────────────────────────
        print("    → Priority 3 (Tavily)…")
        unemp = _tavily_search(
            "Kitchener-Cambridge-Waterloo CMA unemployment rate 2026 "
            "Statistics Canada Labour Force Survey percent",
            lo=2.0, hi=15.0,
        )
        if unemp is not None:
            employed = round(100.0 - unemp, 1)
            print(f"    ✓ Priority 3 (Tavily): regional_employment = {employed:.1f}% "
                  f"(unemployment {unemp:.1f}%)")
            return employed, "tavily"
        return None, "tavily"

    def run_and_store(self) -> dict[str, Any]:
        now = datetime.now(timezone.utc)
        results: dict[str, Any] = {}

        unemp_val, unemp_src = self.fetch_unemployment_rate()
        status = "success" if unemp_src == "statcan" else ("fallback" if unemp_val else "failed")
        src_name = _SRC_STATCAN if unemp_src == "statcan" else _SRC_TAVILY
        print(f"  unemployment_rate: {unemp_val} ({status} via {unemp_src})")
        if unemp_val is not None:
            _store(
                "unemployment_rate", self.DOMAIN,
                "Unemployment rate (Waterloo Region)",
                unemp_val, "%", status, now, source_name=src_name,
            )
        results["unemployment_rate"] = {"value": unemp_val, "status": status, "source": unemp_src}

        emp_val, emp_src = self.fetch_employment_rate()
        status = "success" if emp_src == "statcan" else ("fallback" if emp_val else "failed")
        src_name = _SRC_STATCAN if emp_src == "statcan" else _SRC_TAVILY
        print(f"  regional_employment: {emp_val} ({status} via {emp_src})")
        if emp_val is not None:
            _store(
                "regional_employment", self.DOMAIN,
                "Strong Regional Employment",
                emp_val, "percent_employed", status, now, source_name=src_name,
            )
        results["regional_employment"] = {"value": emp_val, "status": status, "source": emp_src}

        return results
