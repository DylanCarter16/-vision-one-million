"""
Healthcare fetcher — Ontario LTC scrape + Tavily for ER waits and doctor access.
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

_LTC_URL = "https://www.ontario.ca/locations/longtermcare/search/?n=Waterloo%2C+ON"


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


class HealthcareFetcher:
    """Fetches real healthcare metrics for Waterloo Region."""

    DOMAIN = "healthcare"

    def fetch_ltc_waitlist(self) -> tuple[float | None, str]:
        """
        Scrape Ontario's LTC locator for Waterloo Region facilities and compute
        an availability proxy (beds available / total beds * 100).
        Falls back to Tavily.
        """
        try:
            from bs4 import BeautifulSoup

            resp = requests.get(_LTC_URL, headers=_HEADERS, timeout=_TIMEOUT)
            resp.raise_for_status()
            soup = BeautifulSoup(resp.text, "html.parser")
            text = soup.get_text(" ", strip=True)

            # Look for patterns like "123 beds available" or "waitlist: 456"
            # Ontario page typically shows "X bed(s) available" per facility
            avail_matches = re.findall(
                r"(\d+)\s+(?:bed|beds|spaces?)\s+(?:available|vacant|open)",
                text, re.IGNORECASE,
            )
            total_matches = re.findall(
                r"(\d+)\s+(?:total\s+)?(?:licensed\s+)?beds?",
                text, re.IGNORECASE,
            )
            if avail_matches and total_matches:
                avail = sum(int(x) for x in avail_matches)
                total = sum(int(x) for x in total_matches[:len(avail_matches)])
                if total > 0:
                    pct = round((avail / total) * 100, 1)
                    logger.info("LTC availability (Waterloo): %.1f%%", pct)
                    return pct, "ontario_ltc"

            # Fallback: look for any explicit percentage near "available" or "waitlist"
            pct_match = re.search(
                r"(\d+(?:\.\d+)?)\s*%[^%]{0,60}(?:available|waitlist|capacity)",
                text, re.IGNORECASE,
            )
            if pct_match:
                val = float(pct_match.group(1))
                if 0.0 <= val <= 100.0:
                    return val, "ontario_ltc"

            logger.warning("LTC page fetched but no availability numbers found (%d bytes)", len(resp.text))

        except Exception as exc:
            logger.warning("LTC scrape failed: %s", exc)

        logger.info("Falling back to Tavily for LTC waitlist")
        val = _tavily_search(
            "Waterloo Region long term care waitlist 2025 Ontario beds available percent",
            lo=0.0, hi=100.0,
        )
        return val, "tavily"

    def fetch_er_wait_times(self) -> tuple[float | None, str]:
        """
        Use Tavily to find the most recent ER wait time (hours) for Waterloo Region.
        Tries two queries: regional summary, then specific hospitals.
        """
        for query in (
            "Waterloo Region hospital emergency department wait times 2025 hours",
            "Grand River Hospital Cambridge Memorial Hospital ER wait time 2025 hours",
        ):
            val = _tavily_search(query, lo=0.5, hi=24.0)
            if val is not None:
                logger.info("ER wait time (Tavily): %.1f hrs", val)
                return val, "tavily"

        return None, "tavily"

    def fetch_doctor_access(self) -> tuple[float | None, str]:
        """
        Use Tavily to find % of Waterloo Region residents with a family doctor.
        Converts "X% without" to "100-X% with" when the framing is inverted.
        """
        query = "Waterloo Region percent residents with family doctor 2025"
        val = _tavily_search(query, lo=50.0, hi=100.0)
        if val is not None:
            logger.info("Doctor access (Tavily): %.1f%%", val)
            return val, "tavily"

        # Try the "without" framing and invert
        without_val = _tavily_search(
            "Waterloo Region residents without family doctor percent 2025",
            lo=0.0, hi=50.0,
        )
        if without_val is not None:
            inverted = round(100.0 - without_val, 1)
            logger.info("Doctor access (inverted from without): %.1f%%", inverted)
            return inverted, "tavily"

        return None, "tavily"

    def fetch_mental_health(self) -> tuple[float | None, str]:
        """
        Use Tavily to find mental health and addiction service capacity in Waterloo Region.
        Returns an estimated % of need being met (0-100).
        """
        val = _tavily_search(
            "Waterloo Region mental health addiction services funding capacity 2025 percent",
            lo=0.0, hi=100.0,
        )
        if val is not None:
            logger.info("Mental health support (Tavily): %.1f%%", val)
        return val, "tavily"

    def run_and_store(self) -> dict[str, Any]:
        now = datetime.now(timezone.utc)
        results: dict[str, Any] = {}

        ltc_val, ltc_src = self.fetch_ltc_waitlist()
        status = "success" if ltc_src == "ontario_ltc" else ("fallback" if ltc_val else "failed")
        print(f"  ltc_access: {ltc_val} ({status} via {ltc_src})")
        if ltc_val is not None:
            _store("ltc_access", self.DOMAIN, "Improved Access to LTC",
                   ltc_val, "percent", status, now)
        results["ltc_access"] = {"value": ltc_val, "status": status, "source": ltc_src}

        er_val, er_src = self.fetch_er_wait_times()
        # For ER waits: lower is better; target is 3.0 hrs
        if er_val is not None:
            if er_val < 3.0:
                er_status = "success"
            elif er_val < 4.0:
                er_status = "fallback"   # on track but not primary
            else:
                er_status = "fallback"
        else:
            er_status = "failed"
        print(f"  er_wait_target: {er_val} ({er_status} via {er_src})")
        if er_val is not None:
            _store("er_wait_target", self.DOMAIN, "Emergency Department Wait Times",
                   er_val, "hours", er_status, now)
        results["er_wait_target"] = {"value": er_val, "status": er_status, "source": er_src}

        doc_val, doc_src = self.fetch_doctor_access()
        status = "fallback" if doc_val else "failed"
        print(f"  residents_with_doctor: {doc_val} ({status} via {doc_src})")
        if doc_val is not None:
            _store("residents_with_doctor", self.DOMAIN, "Residents Connected to a Doctor",
                   doc_val, "percent", status, now)
        results["residents_with_doctor"] = {"value": doc_val, "status": status, "source": doc_src}

        mh_val, mh_src = self.fetch_mental_health()
        status = "fallback" if mh_val else "failed"
        print(f"  mental_health_support: {mh_val} ({status} via {mh_src})")
        if mh_val is not None:
            _store("mental_health_support", self.DOMAIN, "Mental Health & Addiction Support",
                   mh_val, "percent", status, now)
        results["mental_health_support"] = {"value": mh_val, "status": status, "source": mh_src}

        return results
