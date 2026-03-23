"""
Modular ingestion engine: API, scrape (BeautifulSoup / Playwright), PDF + OpenAI, Tavily fallback.
"""

from .api_fetcher import APIFetcher
from .base import DataFetcher
from .engine import (
    create_fetcher,
    iter_fetchers,
    load_config,
    load_sources,
    merged_defaults,
    run_all_sources,
)
from .models import FetchResult, SourceConfig
from .pdf_fetcher import PDFFetcher
from .scrape_fetcher import ScrapeFetcher
from .tavily_fallback import TavilyFallback

__all__ = [
    "APIFetcher",
    "DataFetcher",
    "FetchResult",
    "PDFFetcher",
    "ScrapeFetcher",
    "SourceConfig",
    "TavilyFallback",
    "create_fetcher",
    "iter_fetchers",
    "load_config",
    "load_sources",
    "merged_defaults",
    "run_all_sources",
]
