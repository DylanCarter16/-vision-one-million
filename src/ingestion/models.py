"""Shared types for the ingestion pipeline."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Mapping


@dataclass(frozen=True)
class FetchResult:
    """Outcome of a single fetch attempt (primary or fallback)."""

    success: bool
    target_metric: str
    source_id: str
    data: Any = None
    raw: str | bytes | None = None
    error: str | None = None
    source_used: str = "primary"  # "primary" | "tavily" | "openai_extraction"


@dataclass
class SourceConfig:
    """One row from the YAML `sources` list."""

    id: str
    source_url: str
    data_type: str
    target_metric: str
    css_selector_or_api_key: str = ""
    display_name: str = ""
    update_frequency: Mapping[str, Any] | str | None = None
    extra: dict[str, Any] = field(default_factory=dict)

    @classmethod
    def from_mapping(cls, row: Mapping[str, Any]) -> SourceConfig:
        known = {
            "id",
            "display_name",
            "source_url",
            "update_frequency",
            "data_type",
            "target_metric",
            "css_selector_or_api_key",
        }
        extra = {k: v for k, v in row.items() if k not in known}
        return cls(
            id=str(row["id"]),
            display_name=str(row.get("display_name", "")),
            source_url=str(row["source_url"]),
            update_frequency=row.get("update_frequency"),
            data_type=str(row["data_type"]).lower().strip(),
            target_metric=str(row["target_metric"]),
            css_selector_or_api_key=str(row.get("css_selector_or_api_key", "")),
            extra=extra,
        )
