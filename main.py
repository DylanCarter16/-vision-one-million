"""Pipeline entrypoint: fetch current values from all domain fetchers and persist to SQLite."""

from __future__ import annotations

import logging
import sys
from pathlib import Path
from typing import Any

from dotenv import load_dotenv

ROOT = Path(__file__).resolve().parent
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from agent.database import init_db  # noqa: E402
from ingestion.fetchers import (  # noqa: E402
    EmploymentFetcher,
    HealthcareFetcher,
    HousingFetcher,
    PlacemakingFetcher,
    TransportationFetcher,
)

logger = logging.getLogger("vision_one_million.main")

_FETCHERS = [
    EmploymentFetcher,
    HousingFetcher,
    TransportationFetcher,
    HealthcareFetcher,
    PlacemakingFetcher,
]

# Column widths for summary table
_C1, _C2, _C3, _C4 = 32, 14, 10, 10


def _print_summary(all_results: dict[str, dict[str, Any]]) -> None:
    sep = f"+-{'-'*_C1}-+-{'-'*_C2}-+-{'-'*_C3}-+-{'-'*_C4}-+"
    hdr = (
        f"| {'metric_id':<{_C1}} | {'value':>{_C2}} | {'source':<{_C3}} | {'status':<{_C4}} |"
    )
    print(f"\n{sep}")
    print(hdr)
    print(sep)
    for metric_id, info in sorted(all_results.items()):
        val = info.get("value")
        val_str = f"{val:,.2f}" if isinstance(val, float) else (str(val) if val is not None else "N/A")
        src = str(info.get("source") or "—")[:_C2]
        sta = str(info.get("status") or "—")[:_C4]
        print(f"| {metric_id:<{_C1}} | {val_str:>{_C2}} | {src:<{_C3}} | {sta:<{_C4}} |")
    print(sep)


def run_pipeline() -> tuple[int, int]:
    load_dotenv()
    init_db()

    all_results: dict[str, dict[str, Any]] = {}
    successes = 0
    total = 0

    for FetcherClass in _FETCHERS:
        fetcher = FetcherClass()
        print(f"\n>> {fetcher.__class__.__name__}")
        try:
            results = fetcher.run_and_store()
            all_results.update(results)
            for info in results.values():
                total += 1
                if info.get("status") == "success":
                    successes += 1
        except Exception as exc:
            logger.error("%s failed: %s", fetcher.__class__.__name__, exc)

    _print_summary(all_results)

    real_count = sum(1 for i in all_results.values() if i.get("status") == "success")
    fallback_count = sum(1 for i in all_results.values() if i.get("status") == "fallback")
    failed_count = sum(1 for i in all_results.values() if i.get("status") == "failed")

    print(f"\nPipeline complete: {real_count + fallback_count}/{total} metrics updated")
    print(f"  Real source:      {real_count}")
    print(f"  Tavily fallback:  {fallback_count}")
    print(f"  Failed:           {failed_count}")

    return successes, total


def main() -> None:
    logging.basicConfig(level=logging.WARNING, format="%(levelname)s %(message)s")
    run_pipeline()


if __name__ == "__main__":
    main()
