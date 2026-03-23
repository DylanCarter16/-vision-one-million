"""HTTP-based fetcher for official APIs and CSV/flat URLs (StatCan, CMHC exports)."""

from __future__ import annotations

import json
import logging
from typing import Any, Mapping

import requests

from .base import DataFetcher
from .models import FetchResult, SourceConfig

logger = logging.getLogger(__name__)


class APIFetcher(DataFetcher):
    """
    Fetch JSON, CSV, or plain text over HTTPS using `requests`.
    Suitable for StatCan Web Data Service, CMHC table exports, etc.
    """

    def __init__(
        self,
        source: SourceConfig,
        defaults: Mapping[str, Any] | None = None,
        *,
        session_headers: Mapping[str, str] | None = None,
        api_key: str | None = None,
    ) -> None:
        super().__init__(source, defaults, session_headers=session_headers)
        self._api_key = api_key

    def fetch(self) -> FetchResult:
        url = self.source.source_url
        headers = self._default_headers()
        key_hint = self.source.css_selector_or_api_key.strip()
        if key_hint and key_hint.upper() not in ("N/A", "NA", ""):
            if key_hint.isupper() and "_" in key_hint:
                import os

                env_val = os.environ.get(key_hint)
                if env_val:
                    headers["Authorization"] = f"Bearer {env_val}"
            elif self._api_key:
                headers["Authorization"] = f"Bearer {self._api_key}"

        try:
            resp = requests.get(
                url,
                headers=headers,
                timeout=self._timeout(),
            )
            resp.raise_for_status()
        except requests.RequestException as e:
            return FetchResult(
                success=False,
                target_metric=self.source.target_metric,
                source_id=self.source.id,
                error=str(e),
            )

        content_type = (resp.headers.get("Content-Type") or "").lower()
        raw_text = resp.text
        parsed: Any
        if "json" in content_type or raw_text.strip().startswith("{"):
            try:
                parsed = resp.json()
            except json.JSONDecodeError:
                parsed = raw_text
        else:
            parsed = raw_text

        return FetchResult(
            success=True,
            target_metric=self.source.target_metric,
            source_id=self.source.id,
            data=parsed,
            raw=raw_text,
            source_used="primary",
        )
