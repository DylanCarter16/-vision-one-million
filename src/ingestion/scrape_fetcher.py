"""HTML scraping with BeautifulSoup; Playwright for JavaScript-rendered pages."""

from __future__ import annotations

import logging
from typing import Any, Mapping

import requests
from bs4 import BeautifulSoup

from .base import DataFetcher
from .models import FetchResult, SourceConfig

logger = logging.getLogger(__name__)


class ScrapeFetcher(DataFetcher):
    """
    Primary path: `requests` + BeautifulSoup + CSS selector.
    Optional: Playwright when `use_playwright=True` (SPAs, deferred content).
    """

    def __init__(
        self,
        source: SourceConfig,
        defaults: Mapping[str, Any] | None = None,
        *,
        session_headers: Mapping[str, str] | None = None,
        use_playwright: bool = False,
    ) -> None:
        super().__init__(source, defaults, session_headers=session_headers)
        self.use_playwright = use_playwright or bool(
            (source.extra or {}).get("render_javascript")
        )

    def _html_from_requests(self) -> str:
        r = requests.get(
            self.source.source_url,
            headers=self._default_headers(),
            timeout=self._timeout(),
        )
        r.raise_for_status()
        return r.text

    def _html_from_playwright(self) -> str:
        from playwright.sync_api import sync_playwright

        with sync_playwright() as p:
            browser = p.chromium.launch(headless=True)
            try:
                page = browser.new_page(user_agent=self._user_agent() or None)
                page.goto(
                    self.source.source_url,
                    wait_until="networkidle",
                    timeout=int(self._timeout() * 1000),
                )
                return page.content()
            finally:
                browser.close()

    def fetch(self) -> FetchResult:
        selector = (self.source.css_selector_or_api_key or "").strip()
        if not selector or selector.upper() in ("N/A", "NA"):
            return FetchResult(
                success=False,
                target_metric=self.source.target_metric,
                source_id=self.source.id,
                error="css_selector_or_api_key is required for ScrapeFetcher",
            )

        try:
            if self.use_playwright:
                html = self._html_from_playwright()
            else:
                html = self._html_from_requests()
        except Exception as e:
            return FetchResult(
                success=False,
                target_metric=self.source.target_metric,
                source_id=self.source.id,
                error=str(e),
            )

        soup = BeautifulSoup(html, "html.parser")
        elements = soup.select(selector)
        if not elements:
            return FetchResult(
                success=False,
                target_metric=self.source.target_metric,
                source_id=self.source.id,
                raw=html[:8000],
                error=f"No elements matched selector: {selector!r}",
            )

        texts = [el.get_text(" ", strip=True) for el in elements]
        data: Any = texts[0] if len(texts) == 1 else texts

        return FetchResult(
            success=True,
            target_metric=self.source.target_metric,
            source_id=self.source.id,
            data=data,
            raw=html[:8000],
            source_used="primary",
        )
