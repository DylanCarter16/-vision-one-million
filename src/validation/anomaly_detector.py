"""Compare new readings to history; optionally consult OpenAI on large swings."""

from __future__ import annotations

import json
import logging
import re
from typing import Any

from dotenv import load_dotenv
from openai import OpenAI

load_dotenv()

logger = logging.getLogger(__name__)


class AnomalyDetector:
    """
    Uses historical metric dicts to compute percent change vs the latest prior value.
    If |% change| > 50, asks GPT-4o-mini whether the jump is likely data error or real.
    """

    def __init__(
        self,
        historical_metric_dicts: list[dict[str, Any]],
        *,
        model: str = "gpt-4o-mini",
    ) -> None:
        self._model = model
        self._by_metric: dict[str, list[tuple[tuple[int, int | None], float]]] = {}
        for row in historical_metric_dicts:
            mid = row.get("metric_id")
            if mid is None or str(mid).strip() == "":
                continue
            mid = str(mid)
            val = row.get("value")
            if val is None:
                continue
            try:
                v = float(val)
            except (TypeError, ValueError):
                continue
            year = int(row["year"])
            month = row.get("month")
            month_i = int(month) if month is not None else None
            key = (year, month_i)
            self._by_metric.setdefault(mid, []).append((key, v))

        for mid in self._by_metric:
            self._by_metric[mid].sort(
                key=lambda x: (x[0][0], x[0][1] if x[0][1] is not None else 13)
            )

    def _previous_value(self, metric_id: str) -> float | None:
        series = self._by_metric.get(metric_id)
        if not series:
            return None
        return series[-1][1]

    def check(self, new_value: float, metric_id: str) -> dict[str, Any]:
        """
        Returns {"flagged": bool, "reason": str, "requires_human_review": bool}.
        """
        prev = self._previous_value(metric_id)
        if prev is None:
            return {
                "flagged": False,
                "reason": "No historical baseline for this metric_id.",
                "requires_human_review": False,
            }

        if prev == 0:
            return {
                "flagged": True,
                "reason": "Previous value is zero; percent change is undefined.",
                "requires_human_review": True,
            }

        pct_change = (new_value - prev) / prev * 100.0
        if abs(pct_change) <= 50.0:
            return {
                "flagged": False,
                "reason": f"Within tolerance: {pct_change:.1f}% change from prior.",
                "requires_human_review": False,
            }

        llm = self._llm_assess(metric_id, prev, new_value, pct_change)
        if llm is not None:
            return llm

        return {
            "flagged": True,
            "reason": "Large change and LLM assessment failed; default to human review.",
            "requires_human_review": True,
        }

    def _llm_assess(
        self,
        metric_id: str,
        old_value: float,
        new_value: float,
        pct_change: float,
    ) -> dict[str, Any] | None:
        prompt = (
            f"You are reviewing a regional scorecard data point.\n"
            f"Metric id: {metric_id!r}\n"
            f"Previous value: {old_value}\n"
            f"New value: {new_value}\n"
            f"Percent change: {pct_change:.2f}%\n\n"
            "Is this likely a data error (typo, unit mix-up, bad scrape) or a plausible "
            "real-world change? Reply with a single JSON object only, keys:\n"
            '"flagged" (boolean, true if likely data error),\n'
            '"reason" (short string),\n'
            '"requires_human_review" (boolean, true if uncertain or high stakes).\n'
        )
        try:
            client = OpenAI()
            resp = client.chat.completions.create(
                model=self._model,
                messages=[
                    {
                        "role": "system",
                        "content": "You respond with valid JSON only, no markdown.",
                    },
                    {"role": "user", "content": prompt},
                ],
                temperature=0,
            )
            raw = (resp.choices[0].message.content or "").strip()
            m = re.search(r"\{[\s\S]*\}", raw)
            if not m:
                logger.warning("OpenAI returned no JSON object: %s", raw[:200])
                return None
            data = json.loads(m.group())
            return {
                "flagged": bool(data.get("flagged", True)),
                "reason": str(data.get("reason", "")),
                "requires_human_review": bool(data.get("requires_human_review", True)),
            }
        except Exception as e:
            logger.exception("OpenAI call failed during anomaly check: %s", e)
            return None
