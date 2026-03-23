"""
Source registry: loads config/sources.yaml and provides lookup helpers.
"""

from __future__ import annotations

from collections import defaultdict
from pathlib import Path
from typing import Any

import yaml

_CONFIG_PATH = Path(__file__).resolve().parents[2] / "config" / "sources.yaml"


def load_sources(config_path: Path = _CONFIG_PATH) -> dict[str, list[dict[str, Any]]]:
    """Return sources grouped by domain as ``{domain: [source_dict, ...]}``.

    Each source dict is the raw YAML entry enriched with a ``domain`` key.
    """
    with open(config_path, encoding="utf-8") as fh:
        cfg = yaml.safe_load(fh) or {}

    raw: dict[str, list[dict]] = cfg.get("sources") or {}
    result: dict[str, list[dict[str, Any]]] = {}
    for domain, entries in raw.items():
        enriched = []
        for entry in entries or []:
            enriched.append({**entry, "domain": domain})
        result[domain] = enriched
    return result


def get_sources_by_type(
    config_path: Path = _CONFIG_PATH,
) -> dict[str, list[dict[str, Any]]]:
    """Return all sources grouped by fetch type (``api``, ``pdf``, ``web_scrape``)."""
    by_type: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for entries in load_sources(config_path).values():
        for src in entries:
            by_type[src.get("type", "unknown")].append(src)
    return dict(by_type)


def get_sources_for_metric(
    metric_id: str,
    config_path: Path = _CONFIG_PATH,
) -> list[dict[str, Any]]:
    """Return every source whose ``metrics`` list includes *metric_id*."""
    matches: list[dict[str, Any]] = []
    for entries in load_sources(config_path).values():
        for src in entries:
            if metric_id in (src.get("metrics") or []):
                matches.append(src)
    return matches


def print_registry_summary(config_path: Path = _CONFIG_PATH) -> None:
    """Print a human-readable summary: counts by domain and by fetch type."""
    by_domain = load_sources(config_path)
    by_type: dict[str, int] = defaultdict(int)
    total = 0

    print("=" * 52)
    print("  Vision One Million — Source Registry Summary")
    print("=" * 52)
    print(f"\n{'Domain':<18} {'Sources':>7}  Types")
    print("-" * 52)
    for domain, entries in by_domain.items():
        type_counts: dict[str, int] = defaultdict(int)
        for src in entries:
            t = src.get("type", "unknown")
            type_counts[t] += 1
            by_type[t] += 1
            total += 1
        type_str = ", ".join(f"{t}×{n}" for t, n in sorted(type_counts.items()))
        print(f"  {domain:<16} {len(entries):>7}  {type_str}")

    print("-" * 52)
    print(f"  {'TOTAL':<16} {total:>7}")
    print()
    print("By fetch type:")
    for t, n in sorted(by_type.items()):
        print(f"  {t:<14} {n:>3} sources")
    print()

    # Build reverse index: metric -> source count
    metric_index: dict[str, int] = defaultdict(int)
    for entries in by_domain.values():
        for src in entries:
            for m in src.get("metrics") or []:
                metric_index[m] += 1

    print(f"Unique metrics covered: {len(metric_index)}")
    multi = {m: n for m, n in metric_index.items() if n > 1}
    if multi:
        print("Metrics with multiple sources:")
        for m, n in sorted(multi.items()):
            print(f"  {m:<35} {n} sources")
    print("=" * 52)
