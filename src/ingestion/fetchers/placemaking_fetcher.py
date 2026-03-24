"""
Placemaking fetcher — Climate Action dashboard scrape + StatCan crime API + Tavily.
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

_CLIMATE_URLS = [
    "https://dashboard.climateactionwr.ca/actions/3.1.7",
    "https://dashboard.climateactionwr.ca/actions/3.1.8",
    "https://dashboard.climateactionwr.ca/",
]
# StatCan police-reported crime: Table 35-10-0191-01
# Coord: Geography=1 (Canada), CSD/CMA filter not available without filtering;
# using the KCW vector approach via a simple text search as fallback.
_STATCAN_CRIME_URL = (
    "https://www150.statcan.gc.ca/t1/tbl1/en/dtbl/"
    "getDataFromCubePidCoordAndLatestNPeriods/3510019101/1.1.1.1.1/5"
)


def _tavily_search(query: str, lo: float, hi: float) -> float | None:
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
        for m in re.findall(r"\d+(?:\.\d+)?", text):
            try:
                v = float(m)
                if lo <= v <= hi:
                    candidates.append(v)
            except ValueError:
                continue
        return candidates[0] if candidates else None
    except Exception as exc:
        logger.warning("Tavily search failed: %s", exc)
        return None


_SRC_CLIMATE = "Climate Action Waterloo Region"
_SRC_STATCAN = "Statistics Canada Crime Severity Index"
_SRC_WRDSB   = "WRDSB Long-Term Accommodation Plan"
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


class PlacemakingFetcher:
    """Fetches real placemaking metrics for Waterloo Region."""

    DOMAIN = "placemaking"

    def fetch_ghg_reduction(self) -> tuple[float | None, str]:
        """
        Scrape Climate Action Waterloo Region dashboard for GHG reduction progress.
        Tries multiple action pages before falling back to Tavily.
        """
        from bs4 import BeautifulSoup

        for url in _CLIMATE_URLS:
            try:
                resp = requests.get(url, headers=_HEADERS, timeout=_TIMEOUT)
                resp.raise_for_status()
                soup = BeautifulSoup(resp.text, "html.parser")
                text = soup.get_text(" ", strip=True)

                # Look for explicit reduction percentage near keywords
                for pattern in (
                    r"(\d+(?:\.\d+)?)\s*%\s*(?:reduction|reduced|below|decrease)",
                    r"(?:reduction|reduced|below|decrease)[^%]{0,80}?(\d+(?:\.\d+)?)\s*%",
                    r"(\d+(?:\.\d+)?)\s*%\s*(?:of\s+)?(?:target|goal|objective)",
                ):
                    m = re.search(pattern, text, re.IGNORECASE)
                    if m:
                        val = float(m.group(1))
                        if 0.0 <= val <= 100.0:
                            logger.info("GHG reduction from %s: %.1f%%", url, val)
                            return val, "climate_action_dashboard"

                # Grab any prominent percentage on the page (first in a header/strong)
                for tag in soup.find_all(["h1", "h2", "h3", "strong", "b"]):
                    tag_text = tag.get_text(" ", strip=True)
                    pct = re.search(r"(\d+(?:\.\d+)?)\s*%", tag_text)
                    if pct:
                        val = float(pct.group(1))
                        if 0.0 < val <= 100.0:
                            logger.info("GHG reduction (prominent pct) from %s: %.1f%%", url, val)
                            return val, "climate_action_dashboard"

            except Exception as exc:
                logger.warning("Climate dashboard %s failed: %s", url, exc)

        logger.info("Falling back to Tavily for GHG reduction")
        # Waterloo Region's 2022 inventory showed ~15-20% reduction from 2010 baseline.
        # Tighten range to avoid grabbing unrelated percentages.
        val = _tavily_search(
            "Waterloo Region greenhouse gas GHG emissions percent reduction below 2010 baseline 2023 2024",
            lo=5.0, hi=40.0,
        )
        return val, "tavily"

    def fetch_childcare_access(self) -> tuple[float | None, str]:
        """Tavily search for childcare space availability in Waterloo Region."""
        val = _tavily_search(
            "Waterloo Region licensed childcare spaces availability percent 2025",
            lo=0.0, hi=100.0,
        )
        if val is not None:
            logger.info("Childcare access (Tavily): %.1f%%", val)
        return val, "tavily"

    def fetch_community_safety(self) -> tuple[float | None, str]:
        """
        Try StatCan crime severity index API, then fall back to Tavily.
        Converts the Crime Severity Index to a 0-100 scale relative to a
        baseline of 100 (national average); lower CSI = higher safety score.
        """
        try:
            resp = requests.get(_STATCAN_CRIME_URL, headers=_HEADERS, timeout=_TIMEOUT)
            resp.raise_for_status()
            body = resp.json()
            if isinstance(body, list) and body:
                points = body[0].get("object", {}).get("vectorDataPoint", [])
                for pt in points:
                    raw = pt.get("value")
                    if raw is not None:
                        try:
                            csi = float(raw)
                            # Convert CSI to a safety % score:
                            # CSI=100 (national avg) → 50%, CSI=50 → 75%, CSI=150 → 25%
                            safety_pct = round(max(0.0, min(100.0, 100.0 - (csi - 50.0) / 2.0)), 1)
                            logger.info("Crime Severity Index (StatCan): %.1f → safety %.1f%%", csi, safety_pct)
                            return safety_pct, "statcan_crime"
                        except (TypeError, ValueError):
                            continue
        except Exception as exc:
            logger.warning("StatCan crime API failed: %s", exc)

        logger.info("Falling back to Tavily for community safety")
        # Tavily: search for crime rate or safety index as a direct percentage
        val = _tavily_search(
            "Waterloo Region crime severity index 2024 Statistics Canada",
            lo=30.0, hi=200.0,  # CSI range
        )
        if val is not None:
            # Convert CSI to safety %
            safety_pct = round(max(0.0, min(100.0, 100.0 - (val - 50.0) / 2.0)), 1)
            logger.info("Community safety from Tavily CSI %.1f → %.1f%%", val, safety_pct)
            return safety_pct, "tavily"

        return None, "tavily"

    def fetch_school_spaces(self) -> tuple[float | None, str]:
        """
        Try to download the WRDSB Long-Term Accommodation Plan PDF and extract
        a utilisation percentage using PyPDF2. Falls back to Tavily.
        """
        _WRDSB_URL = (
            "https://www.wrdsb.ca/planning/wp-content/uploads/sites/5/"
            "2020-2030-WRDSB-Long-Term-Accommodation-Plan-FINAL.pdf"
        )
        try:
            import io
            import PyPDF2

            resp = requests.get(_WRDSB_URL, headers=_HEADERS, timeout=30)
            resp.raise_for_status()
            reader = PyPDF2.PdfReader(io.BytesIO(resp.content))
            text = " ".join(
                page.extract_text() or "" for page in reader.pages[:10]
            )
            # Look for utilisation/capacity percentages
            for pattern in (
                r"(\d+(?:\.\d+)?)\s*%\s*(?:utiliz|capacity|occupied)",
                r"(?:utiliz|capacity|occupied)[^\d]{0,60}(\d+(?:\.\d+)?)\s*%",
            ):
                m = re.search(pattern, text, re.IGNORECASE)
                if m:
                    val = float(m.group(1))
                    if 0.0 < val <= 150.0:
                        logger.info("WRDSB school utilisation from PDF: %.1f%%", val)
                        return val, "wrdsb_pdf"
            logger.warning("WRDSB PDF downloaded but no utilisation % found")
        except Exception as exc:
            logger.warning("WRDSB PDF fetch failed: %s", exc)

        logger.info("Falling back to Tavily for school spaces")
        val = _tavily_search(
            "WRDSB school capacity utilization 2025 Waterloo Region percent",
            lo=0.0, hi=150.0,
        )
        return val, "tavily"

    def fetch_tourism(self) -> tuple[float | None, str]:
        """Tavily search for tourism/recreation activity in Waterloo Region."""
        val = _tavily_search(
            "Waterloo Region tourism visitors revenue 2024 2025 percent growth",
            lo=0.0, hi=100.0,
        )
        if val is not None:
            logger.info("Tourism/recreation (Tavily): %.1f%%", val)
        return val, "tavily"

    def fetch_social_infrastructure(self) -> tuple[float | None, str]:
        """Tavily search for social infrastructure investment progress."""
        val = _tavily_search(
            "Waterloo Region community centers social infrastructure investment 2025 percent",
            lo=0.0, hi=100.0,
        )
        if val is not None:
            logger.info("Social infrastructure (Tavily): %.1f%%", val)
        return val, "tavily"

    def run_and_store(self) -> dict[str, Any]:
        now = datetime.now(timezone.utc)
        results: dict[str, Any] = {}

        ghg_val, ghg_src = self.fetch_ghg_reduction()
        status = "success" if ghg_src == "climate_action_dashboard" else ("fallback" if ghg_val else "failed")
        src_name = _SRC_CLIMATE if ghg_src == "climate_action_dashboard" else _SRC_TAVILY
        print(f"  ghg_reduction: {ghg_val} ({status} via {ghg_src})")
        if ghg_val is not None:
            _store("ghg_reduction", self.DOMAIN, "Reducing Greenhouse Gases",
                   ghg_val, "percent", status, now, source_name=src_name)
        results["ghg_reduction"] = {"value": ghg_val, "status": status, "source": ghg_src}

        cc_val, cc_src = self.fetch_childcare_access()
        status = "fallback" if cc_val else "failed"
        print(f"  childcare_access: {cc_val} ({status} via {cc_src})")
        if cc_val is not None:
            _store("childcare_access", self.DOMAIN, "Childcare for Everyone Who Needs It",
                   cc_val, "percent", status, now, source_name=_SRC_TAVILY)
        results["childcare_access"] = {"value": cc_val, "status": status, "source": cc_src}

        cs_val, cs_src = self.fetch_community_safety()
        status = "success" if cs_src == "statcan_crime" else ("fallback" if cs_val else "failed")
        src_name = _SRC_STATCAN if cs_src == "statcan_crime" else _SRC_TAVILY
        print(f"  community_safety: {cs_val} ({status} via {cs_src})")
        if cs_val is not None:
            _store("community_safety", self.DOMAIN, "Creating a Safer Community",
                   cs_val, "percent", status, now, source_name=src_name)
        results["community_safety"] = {"value": cs_val, "status": status, "source": cs_src}

        ss_val, ss_src = self.fetch_school_spaces()
        status = "success" if ss_src == "wrdsb_pdf" else ("fallback" if ss_val else "failed")
        src_name = _SRC_WRDSB if ss_src == "wrdsb_pdf" else _SRC_TAVILY
        print(f"  school_spaces: {ss_val} ({status} via {ss_src})")
        if ss_val is not None:
            _store("school_spaces", self.DOMAIN, "Increase Spaces in Schools",
                   ss_val, "percent", status, now, source_name=src_name)
        results["school_spaces"] = {"value": ss_val, "status": status, "source": ss_src}

        tr_val, tr_src = self.fetch_tourism()
        status = "fallback" if tr_val else "failed"
        print(f"  tourism_recreation: {tr_val} ({status} via {tr_src})")
        if tr_val is not None:
            _store("tourism_recreation", self.DOMAIN, "Tourism & Recreation Facilities",
                   tr_val, "percent", status, now, source_name=_SRC_TAVILY)
        results["tourism_recreation"] = {"value": tr_val, "status": status, "source": tr_src}

        si_val, si_src = self.fetch_social_infrastructure()
        status = "fallback" if si_val else "failed"
        print(f"  social_infrastructure: {si_val} ({status} via {si_src})")
        if si_val is not None:
            _store("social_infrastructure", self.DOMAIN, "Increasing Social Infrastructure",
                   si_val, "percent", status, now, source_name=_SRC_TAVILY)
        results["social_infrastructure"] = {"value": si_val, "status": status, "source": si_src}

        return results
