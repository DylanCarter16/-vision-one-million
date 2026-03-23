"""Pandas-based cleaning for scorecard tabular data."""

from __future__ import annotations

from typing import Final, Literal

import pandas as pd

MetricType = Literal["housing", "transportation", "healthcare", "employment"]

_KEY_METRIC_COLUMNS: Final[dict[MetricType, list[str]]] = {
    "housing": ["housing_starts", "avg_home_price", "vacancy_rate", "year"],
    "transportation": ["transit_ridership", "bike_lane_km", "year"],
    "healthcare": ["er_wait_hours", "pct_no_family_doctor", "year"],
    "employment": ["unemployment_rate", "tech_jobs_total", "year"],
}

# Canonical label for the Kitchener–Waterloo CMA and common aliases
_KW_CANONICAL: Final[str] = "Kitchener-Cambridge-Waterloo"
_GEOGRAPHY_ALIASES: Final[dict[str, str]] = {
    "kw": _KW_CANONICAL,
    "kitchener-waterloo": _KW_CANONICAL,
    "kitchener waterloo": _KW_CANONICAL,
    "kitchener–waterloo": _KW_CANONICAL,
    "k-w": _KW_CANONICAL,
    "k/w": _KW_CANONICAL,
    "waterloo region": _KW_CANONICAL,
    "region of waterloo": _KW_CANONICAL,
}

_DEFAULT_NON_NUMERIC_COLS: Final[frozenset[str]] = frozenset(
    {"region", "geography", "metric_id", "source_status", "status"}
)


class DataCleaner:
    """Column-oriented cleaning helpers for regional scorecard DataFrames."""

    def __init__(
        self,
        *,
        region_column: str = "region",
        non_numeric_columns: frozenset[str] | set[str] | None = None,
    ) -> None:
        self.region_column = region_column
        skip = set(_DEFAULT_NON_NUMERIC_COLS)
        skip.add(region_column)
        if non_numeric_columns:
            skip |= set(non_numeric_columns)
        self._non_numeric_columns = skip

    def clean_numeric(self, df: pd.DataFrame) -> pd.DataFrame:
        """Strip commas and % from string-like cells and coerce to float where possible."""
        out = df.copy()
        for col in out.columns:
            if col in self._non_numeric_columns:
                continue
            ser = out[col]
            if not (ser.dtype == object or pd.api.types.is_string_dtype(ser)):
                continue
            cleaned = (
                ser.astype(str)
                .str.replace(",", "", regex=False)
                .str.replace("%", "", regex=False)
                .str.strip()
            )
            converted = pd.to_numeric(cleaned, errors="coerce")
            out[col] = converted
        return out

    def drop_nulls(self, df: pd.DataFrame, metric_type: MetricType) -> pd.DataFrame:
        """Drop rows with nulls in domain key metric columns (must exist on the frame)."""
        cols = [c for c in _KEY_METRIC_COLUMNS[metric_type] if c in df.columns]
        if not cols:
            return df
        return df.dropna(subset=cols, how="any")

    def remove_duplicates(self, df: pd.DataFrame) -> pd.DataFrame:
        """Deduplicate on metric_id, year, and month when present."""
        subset = ["metric_id", "year"]
        if "month" in df.columns:
            subset.append("month")
        missing = [c for c in subset if c not in df.columns]
        if missing:
            raise ValueError(f"remove_duplicates requires columns {subset}; missing: {missing}")
        return df.drop_duplicates(subset=subset, keep="last")

    def normalize_geography(self, df: pd.DataFrame) -> pd.DataFrame:
        """Map known region aliases to a single canonical spelling."""
        if self.region_column not in df.columns:
            return df
        out = df.copy()
        col = out[self.region_column].astype(str).str.strip()

        def _norm(val: str) -> str:
            key = val.casefold().strip()
            return _GEOGRAPHY_ALIASES.get(key, val)

        out[self.region_column] = col.map(_norm)
        return out

    def clean(self, df: pd.DataFrame, metric_type: MetricType) -> pd.DataFrame:
        """Run clean_numeric → drop_nulls → remove_duplicates → normalize_geography."""
        result = self.clean_numeric(df)
        result = self.drop_nulls(result, metric_type)
        result = self.remove_duplicates(result)
        result = self.normalize_geography(result)
        return result
