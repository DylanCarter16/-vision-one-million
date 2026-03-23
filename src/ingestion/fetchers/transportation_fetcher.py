"""
Transportation fetcher — GRT performance page (BeautifulSoup) + Tavily fallback.
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

_HEADERS = {"User-Agent": "VisionOneMillion/1.0 (+https://github.com/DylanCarter16/-vision-one-million)"}
_TIMEOUT = 20

_GRT_URL = "https://www.grt.ca/en/about-grt/performance-measures.aspx"


def _tavily_search(query: str, lo: float = float("-inf"), hi: float = float("inf")) -> float | None:
    api_key = os.environ.get("TAVILY_API_KEY", "")
    if not api_key:
        logger.warning("TAVILY_API_KEY not set; skipping Tavily fallback")
        return None
    try:
        from tavily import TavilyClient
        client = TavilyClient(api_key=api_key)
        resp = client.search(query=query, max_results=5)
        text = " ".join((r.get("content") or "") for r in (resp.get("results") or []))
        candidates = []
        for m in re.findall(r"\d[\d,]*(?:\.\d+)?", text):
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


def _store(
    metric_id: str,
    domain: str,
    label: str,
    value: float,
    unit: str,
    status: str,
    now: datetime,
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
            "flagged": 0,
            "in_human_review": 0,
            "timestamp": now.isoformat(),
        }
    )


class TransportationFetcher:
    """Fetches real transit ridership data from the GRT performance page."""

    DOMAIN = "transportation"

    def fetch_grt_ridership(self) -> tuple[float | None, str]:
        """
        Scrape the GRT performance measures page for monthly boardings.
        Looks for large numbers (>500k) near transit/ridership keywords.
        Falls back to Tavily if the page is unavailable or yields nothing.
        """
        try:
            from bs4 import BeautifulSoup

            resp = requests.get(_GRT_URL, headers=_HEADERS, timeout=_TIMEOUT)
            resp.raise_for_status()
            soup = BeautifulSoup(resp.text, "html.parser")

            # Strategy 1: table cells — GRT publishes performance data in tables
            for td in soup.find_all(["td", "th", "li", "span", "p"]):
                cell_text = td.get_text(" ", strip=True)
                # Look for comma-formatted large integers
                for m in re.findall(r"\b(\d{1,2},\d{3},\d{3})\b", cell_text):
                    try:
                        val = float(m.replace(",", ""))
                        if 500_000 <= val <= 5_000_000:
                            logger.info("GRT ridership from table: %s", val)
                            return val, "grt"
                    except ValueError:
                        continue

            # Strategy 2: full page text — keyword proximity
            text = soup.get_text(" ", strip=True)
            ridership_match = re.search(
                r"(?:ridership|boardings?|passenger trips?)[^\d]{0,80}?"
                r"(\d{1,2},\d{3},\d{3}|\d{6,7})",
                text,
                re.IGNORECASE,
            )
            if ridership_match:
                val = float(ridership_match.group(1).replace(",", ""))
                if 500_000 <= val <= 5_000_000:
                    logger.info("GRT ridership (keyword): %s", val)
                    return val, "grt"

            # Strategy 3: any 7-digit number in range
            all_nums = [float(m.replace(",", "")) for m in re.findall(r"\d[\d,]{5,}", text)]
            candidates = [n for n in all_nums if 500_000 <= n <= 5_000_000]
            if candidates:
                val = candidates[0]
                logger.info("GRT ridership (heuristic): %s", val)
                return val, "grt"

            logger.warning("GRT page fetched (%d bytes) but ridership not found", len(resp.text))

        except Exception as exc:
            logger.warning("GRT page scrape failed: %s", exc)

        logger.info("Falling back to Tavily for GRT ridership")
        val = _tavily_search(
            "Grand River Transit ridership 2025 monthly boardings Waterloo Region",
            lo=500_000, hi=5_000_000,
        )
        return val, "tavily"

    def run_and_store(self) -> dict[str, Any]:
        now = datetime.now(timezone.utc)
        results: dict[str, Any] = {}

        rid_val, rid_src = self.fetch_grt_ridership()
        status = "success" if rid_src == "grt" else ("fallback" if rid_val else "failed")
        print(f"  transit_ridership_target: {rid_val} ({status} via {rid_src})")
        if rid_val is not None:
            _store(
                "transit_ridership_target", self.DOMAIN,
                "Increase Use of Public Transit",
                rid_val, "trips/month", status, now,
            )
        results["transit_ridership_target"] = {"value": rid_val, "status": status, "source": rid_src}

        return results
