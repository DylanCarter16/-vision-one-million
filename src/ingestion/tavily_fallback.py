"""Tavily Search API as a fallback when primary URLs break or move."""

from __future__ import annotations

import json
import logging
import os
from typing import Any

from .models import FetchResult

logger = logging.getLogger(__name__)


class TavilyFallback:
    """
    Uses Tavily to find recent public pages mentioning a regional metric.
    Requires `TAVILY_API_KEY` (or pass `api_key` explicitly).
    """

    def __init__(self, api_key: str | None = None) -> None:
        self.api_key = api_key or os.environ.get("TAVILY_API_KEY")
        self._client: Any = None

    def _get_client(self) -> Any:
        if self._client is not None:
            return self._client
        if not self.api_key:
            raise RuntimeError("TAVILY_API_KEY is not set and no api_key was provided")
        from tavily import TavilyClient

        self._client = TavilyClient(api_key=self.api_key)
        return self._client

    def fallback_for_metric(
        self,
        *,
        target_metric: str,
        source_id: str,
        failed_url: str,
        region: str,
        primary_error: str,
    ) -> FetchResult:
        query_parts = [target_metric.replace("_", " ")]
        if region:
            query_parts.append(region)
        query_parts.append("Canada statistics OR government data")
        query = " ".join(query_parts)

        try:
            client = self._get_client()
            response = client.search(query=query, max_results=5)
        except Exception as e:
            logger.exception("Tavily search failed")
            return FetchResult(
                success=False,
                target_metric=target_metric,
                source_id=source_id,
                error=f"tavily: {e}; primary: {primary_error}",
                source_used="tavily",
            )

        results = response.get("results") if isinstance(response, dict) else None
        if not results:
            return FetchResult(
                success=False,
                target_metric=target_metric,
                source_id=source_id,
                error=f"No Tavily results; primary: {primary_error}",
                raw=json.dumps(response, indent=2)[:4000],
                source_used="tavily",
            )

        payload = {
            "query": query,
            "failed_url": failed_url,
            "primary_error": primary_error,
            "results": [
                {
                    "title": r.get("title"),
                    "url": r.get("url"),
                    "content": r.get("content"),
                }
                for r in results
            ],
        }
        return FetchResult(
            success=True,
            target_metric=target_metric,
            source_id=source_id,
            data=payload,
            raw=json.dumps(payload, indent=2)[:8000],
            source_used="tavily",
        )
