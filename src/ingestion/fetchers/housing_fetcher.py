"""
Housing fetcher — Ontario Data Catalogue API + CMHC BeautifulSoup + Tavily fallback.
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

# Ontario Data Catalogue — Housing Supply Progress, resource 1
_ODC_URL = (
    "https://data.ontario.ca/api/3/action/datastore_search"
    "?resource_id=c922b5b4-9850-40c8-b905-afc3aaa347c0"
    "&limit=100"
)
# CMHC Rental Market Reports landing page
_CMHC_URL = (
    "https://www.cmhc-schl.gc.ca/professionals/housing-markets-data-and-research"
    "/market-reports/rental-market-reports-major-centres"
)


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


_SRC_ODC    = "Ontario Data Catalogue — Housing Supply"
_SRC_CMHC   = "CMHC Rental Market Report"
_SRC_TAVILY = "Tavily Web Search"


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


class HousingFetcher:
    """Fetches real housing metrics for Waterloo Region."""

    DOMAIN = "housing"

    def fetch_housing_starts(self) -> tuple[float | None, str]:
        """
        Query Ontario Data Catalogue API for housing starts data.
        Looks for any record mentioning Waterloo/Kitchener and extracts a
        housing-starts figure. Falls back to Tavily on any error.
        """
        try:
            resp = requests.get(_ODC_URL, headers=_HEADERS, timeout=_TIMEOUT)
            resp.raise_for_status()
            body = resp.json()
            records: list[dict] = body.get("result", {}).get("records") or []
            if not records:
                raise ValueError("Empty records from Ontario Data Catalogue")

            # Search for Waterloo Region / Kitchener rows
            waterloo_keywords = {"waterloo", "kitchener", "cambridge"}
            for rec in records:
                row_text = " ".join(str(v).lower() for v in rec.values())
                if any(kw in row_text for kw in waterloo_keywords):
                    # Try common column names for starts
                    for col in ("Total Units", "TotalUnits", "total_units",
                                "Starts", "starts", "Units", "units", "Value", "value"):
                        raw = rec.get(col)
                        if raw is not None:
                            try:
                                val = float(str(raw).replace(",", ""))
                                if 100 <= val <= 30_000:
                                    logger.info("ODC housing starts for Waterloo: %s", val)
                                    return val, "ontario_data_catalogue"
                            except (ValueError, TypeError):
                                continue

            # No Waterloo-specific row — fall through to Tavily
            logger.warning("ODC returned data but no Waterloo Region housing starts found")

        except Exception as exc:
            logger.warning("Ontario Data Catalogue fetch failed: %s", exc)

        # ── Priority 3: Tavily ───────────────────────────────────────────────
        # Expect annual housing starts ~3,000–10,000 for Waterloo Region
        print("    → Priority 3 (Tavily)…")
        val = _tavily_search(
            "Kitchener-Cambridge-Waterloo Region annual housing starts 2025 CMHC new units",
            lo=1_000, hi=15_000,
        )
        if val is not None:
            print(f"    ✓ Priority 3 (Tavily): building_homes_needed = {val:,.0f} units")
        return val, "tavily"

    def fetch_rental_vacancy(self) -> tuple[float | None, str]:
        """
        Priority 2: Scrape CMHC rental market report for Kitchener vacancy rate.
        Priority 3: Tavily.
        Kitchener vacancy rate historically 1.0–4.0% — reject outliers.
        """
        # ── Priority 2: CMHC scrape ──────────────────────────────────────────
        try:
            from bs4 import BeautifulSoup

            print("    → Priority 2 (CMHC scrape)…")
            resp = requests.get(_CMHC_URL, headers=_HEADERS, timeout=_TIMEOUT)
            resp.raise_for_status()
            soup = BeautifulSoup(resp.text, "html.parser")
            text = soup.get_text(" ", strip=True)

            # Pattern: "Kitchener … X.X%"
            for pattern in (
                r"Kitchener(?:[^%]{0,200}?)(\d+\.\d+)\s*%",
                r"(\d+\.\d+)\s*%(?:[^%]{0,200}?)Kitchener",
            ):
                m = re.search(pattern, text, re.IGNORECASE)
                if m:
                    val = float(m.group(1))
                    if 0.1 <= val <= 8.0:   # KCW range; reject national-level numbers
                        logger.info("CMHC rental vacancy rate for KCW: %.2f%%", val)
                        print(f"    ✓ Priority 2 (CMHC): vacancy_rate = {val:.2f}%")
                        return val, "cmhc"
                    logger.warning("CMHC vacancy value %.2f%% outside KCW expected range", val)

            logger.warning("CMHC page fetched but Kitchener vacancy rate not found")
            print("    ✗ Priority 2 (CMHC): Kitchener vacancy not found in page")

        except Exception as exc:
            logger.warning("CMHC scrape failed: %s", exc)
            print(f"    ✗ Priority 2 (CMHC): {exc}")

        # ── Priority 3: Tavily ───────────────────────────────────────────────
        print("    → Priority 3 (Tavily)…")
        val = _tavily_search(
            "Kitchener Cambridge Waterloo rental vacancy rate 2025 CMHC percent apartment",
            lo=0.1, hi=8.0,
        )
        if val is not None:
            print(f"    ✓ Priority 3 (Tavily): vacancy_rate = {val:.2f}%")
        return val, "tavily"

    def run_and_store(self) -> dict[str, Any]:
        now = datetime.now(timezone.utc)
        results: dict[str, Any] = {}

        starts_val, starts_src = self.fetch_housing_starts()
        status = "success" if starts_src == "ontario_data_catalogue" else (
            "fallback" if starts_val else "failed"
        )
        src_name = _SRC_ODC if starts_src == "ontario_data_catalogue" else _SRC_TAVILY
        print(f"  building_homes_needed: {starts_val} ({status} via {starts_src})")
        if starts_val is not None:
            _store(
                "building_homes_needed", self.DOMAIN,
                "Building the Homes We Need",
                starts_val, "units/yr", status, now, source_name=src_name,
            )
        results["building_homes_needed"] = {"value": starts_val, "status": status, "source": starts_src}

        vac_val, vac_src = self.fetch_rental_vacancy()
        status = "success" if vac_src == "cmhc" else ("fallback" if vac_val else "failed")
        src_name = _SRC_CMHC if vac_src == "cmhc" else _SRC_TAVILY
        print(f"  balanced_rental_market: {vac_val} ({status} via {vac_src})")
        if vac_val is not None:
            _store(
                "balanced_rental_market", self.DOMAIN,
                "Balanced Market for Rental Housing",
                vac_val, "vacancy_pct", status, now, source_name=src_name,
            )
        results["balanced_rental_market"] = {"value": vac_val, "status": status, "source": vac_src}

        return results
