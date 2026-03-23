"""Abstract base fetcher with optional Tavily fallback."""

from __future__ import annotations

import logging
from abc import ABC, abstractmethod
from typing import TYPE_CHECKING, Any, Mapping

from .models import FetchResult, SourceConfig

if TYPE_CHECKING:
    from .tavily_fallback import TavilyFallback

logger = logging.getLogger(__name__)


class DataFetcher(ABC):
    """Base class for all data collection strategies."""

    def __init__(
        self,
        source: SourceConfig,
        defaults: Mapping[str, Any] | None = None,
        *,
        session_headers: Mapping[str, str] | None = None,
    ) -> None:
        self.source = source
        self.defaults = dict(defaults or {})
        self.session_headers = dict(session_headers or {})

    def _timeout(self) -> float:
        ing = self.defaults.get("ingestion_defaults") or {}
        return float(self.defaults.get("timeout_seconds") or ing.get("timeout_seconds", 60))

    def _user_agent(self) -> str | None:
        ing = self.defaults.get("ingestion_defaults") or {}
        return ing.get("user_agent")

    def _default_headers(self) -> dict[str, str]:
        h: dict[str, str] = {}
        ua = self._user_agent()
        if ua:
            h["User-Agent"] = ua
        h.update(self.session_headers)
        return h

    @abstractmethod
    def fetch(self) -> FetchResult:
        """Retrieve data from the primary source."""

    def fetch_with_fallback(
        self,
        tavily: TavilyFallback | None = None,
        *,
        region_hint: str | None = None,
    ) -> FetchResult:
        """
        Try `fetch()`. On failure, optionally search the public web via Tavily
        for the same regional metric.
        """
        try:
            result = self.fetch()
            if result.success:
                return result
            err = result.error or "primary fetch returned success=False"
        except Exception as e:
            err = str(e)
            logger.warning("Primary fetch failed for %s: %s", self.source.id, err)

        if tavily is None:
            return FetchResult(
                success=False,
                target_metric=self.source.target_metric,
                source_id=self.source.id,
                error=err,
                source_used="primary",
            )

        region = region_hint or self._region_default()
        return tavily.fallback_for_metric(
            target_metric=self.source.target_metric,
            source_id=self.source.id,
            failed_url=self.source.source_url,
            region=region,
            primary_error=err,
        )

    def _region_default(self) -> str:
        sc = self.defaults.get("scorecard") or {}
        return str(sc.get("region_default", ""))
