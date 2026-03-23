"""Domain-specific fetchers that pull real data and persist to SQLite."""

from .employment_fetcher import EmploymentFetcher
from .healthcare_fetcher import HealthcareFetcher
from .housing_fetcher import HousingFetcher
from .placemaking_fetcher import PlacemakingFetcher
from .transportation_fetcher import TransportationFetcher

__all__ = [
    "EmploymentFetcher",
    "HealthcareFetcher",
    "HousingFetcher",
    "PlacemakingFetcher",
    "TransportationFetcher",
]
