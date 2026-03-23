"""CLI: `python -m ingestion` (run from repo with `PYTHONPATH=src` or after `pip install -e .`)."""

from __future__ import annotations

import argparse
import json
import logging
import sys
from pathlib import Path

from .engine import run_all_sources
from .tavily_fallback import TavilyFallback


def main() -> None:
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")
    parser = argparse.ArgumentParser(description="Run regional scorecard ingestion from YAML.")
    parser.add_argument(
        "--config",
        type=Path,
        default=Path("config/regional_scorecard_data_sources.yaml"),
        help="Path to data sources YAML",
    )
    parser.add_argument(
        "--no-tavily",
        action="store_true",
        help="Do not use Tavily when primary fetch fails",
    )
    parser.add_argument(
        "--region",
        default=None,
        help="Override region hint for Tavily queries",
    )
    args = parser.parse_args()

    tavily = None if args.no_tavily else TavilyFallback()
    results = run_all_sources(
        args.config,
        tavily=tavily,
        use_tavily_on_failure=not args.no_tavily,
        region_hint=args.region,
    )
    out = [
        {
            "source_id": r.source_id,
            "target_metric": r.target_metric,
            "success": r.success,
            "source_used": r.source_used,
            "error": r.error,
            "data_preview": r.data if isinstance(r.data, (str, int, float)) else "...",
        }
        for r in results
    ]
    print(json.dumps(out, indent=2))
    if not all(r.success for r in results):
        sys.exit(1)


if __name__ == "__main__":
    main()
