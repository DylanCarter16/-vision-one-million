"""Load YAML config, construct fetchers, and run ingestion with optional Tavily fallback."""

from __future__ import annotations

import logging
from pathlib import Path
from typing import Any, Iterator, Mapping

import yaml

from .api_fetcher import APIFetcher
from .base import DataFetcher
from .models import FetchResult, SourceConfig
from .pdf_fetcher import PDFFetcher
from .scrape_fetcher import ScrapeFetcher
from .tavily_fallback import TavilyFallback

logger = logging.getLogger(__name__)


def load_config(path: str | Path) -> dict[str, Any]:
    with open(path, encoding="utf-8") as f:
        return yaml.safe_load(f)


def load_sources(config: Mapping[str, Any]) -> list[SourceConfig]:
    rows = config.get("sources") or []
    return [SourceConfig.from_mapping(row) for row in rows]


def merged_defaults(config: Mapping[str, Any]) -> dict[str, Any]:
    """Flatten YAML so fetchers see scorecard + ingestion_defaults + timeouts."""
    out = dict(config)
    ing = config.get("ingestion_defaults") or {}
    if "timeout_seconds" not in out and ing.get("timeout_seconds") is not None:
        out["timeout_seconds"] = ing["timeout_seconds"]
    out.setdefault("ingestion_defaults", ing)
    out.setdefault("scorecard", config.get("scorecard") or {})
    return out


def create_fetcher(
    source: SourceConfig,
    defaults: Mapping[str, Any] | None = None,
) -> DataFetcher:
    """
    Factory: `api` / `csv` -> APIFetcher; `web_scrape` -> ScrapeFetcher; `pdf` -> PDFFetcher.
    """
    d = dict(defaults or {})
    dt = source.data_type

    if dt in ("api", "csv"):
        return APIFetcher(source, d)
    if dt in ("web_scrape", "scrape", "html"):
        use_pw = bool((source.extra or {}).get("render_javascript"))
        return ScrapeFetcher(source, d, use_playwright=use_pw)
    if dt == "pdf":
        return PDFFetcher(source, d)
    raise ValueError(f"Unknown data_type for {source.id!r}: {dt!r}")


def run_all_sources(
    config_path: str | Path,
    *,
    tavily: TavilyFallback | None = None,
    use_tavily_on_failure: bool = True,
    region_hint: str | None = None,
) -> list[FetchResult]:
    """
    Load YAML, ingest each source. If `use_tavily_on_failure` and `tavily` is provided,
    failed primaries trigger Tavily search for the same metric.
    """
    config = load_config(config_path)
    defaults = merged_defaults(config)
    sources = load_sources(config)
    results: list[FetchResult] = []
    region = region_hint or (defaults.get("scorecard") or {}).get("region_default")

    for src in sources:
        fetcher = create_fetcher(src, defaults)
        if use_tavily_on_failure and tavily is not None:
            results.append(fetcher.fetch_with_fallback(tavily, region_hint=region))
        else:
            results.append(fetcher.fetch())
    return results


def iter_fetchers(config_path: str | Path) -> Iterator[tuple[SourceConfig, DataFetcher]]:
    """Yield (source, fetcher) pairs for custom orchestration."""
    config = load_config(config_path)
    defaults = merged_defaults(config)
    for src in load_sources(config):
        yield src, create_fetcher(src, defaults)
