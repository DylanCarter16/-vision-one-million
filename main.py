"""Pipeline entrypoint: fetch current values from all domain fetchers and persist to SQLite."""

from __future__ import annotations

import logging
import sys
from pathlib import Path

from dotenv import load_dotenv

ROOT = Path(__file__).resolve().parent
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from agent.database import init_db  # noqa: E402
from ingestion.fetchers import EmploymentFetcher, HousingFetcher, TransportationFetcher  # noqa: E402

logger = logging.getLogger("vision_one_million.main")

_FETCHERS = [EmploymentFetcher, HousingFetcher, TransportationFetcher]


def run_pipeline() -> tuple[int, int]:
    load_dotenv()
    init_db()

    successes = 0
    total = 0

    for FetcherClass in _FETCHERS:
        fetcher = FetcherClass()
        print(f"\n▶ {fetcher.__class__.__name__}")
        try:
            results = fetcher.run_and_store()
            for metric_id, info in results.items():
                total += 1
                if info.get("status") == "success":
                    successes += 1
        except Exception as exc:
            logger.error("%s failed: %s", fetcher.__class__.__name__, exc)

    return successes, total


def main() -> None:
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")
    successes, total = run_pipeline()
    print(f"\nPipeline complete: {successes}/{total} metrics fetched via primary source.")


if __name__ == "__main__":
    main()
