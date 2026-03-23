"""Pydantic v2 domain models for validated scorecard metrics."""

from __future__ import annotations

from typing import Any, Literal

from pydantic import (
    AliasChoices,
    BaseModel,
    ConfigDict,
    Field,
    field_validator,
    model_validator,
)

SourceStatus = Literal["success", "fallback", "failed"]


class HousingMetric(BaseModel):
    model_config = ConfigDict(str_strip_whitespace=True, extra="forbid")

    metric_id: str = Field(..., min_length=1)
    source_status: SourceStatus = Field(
        ...,
        validation_alias=AliasChoices("source_status", "status"),
    )
    housing_starts: int = Field(..., gt=0)
    avg_home_price: float = Field(..., gt=0)
    vacancy_rate: float = Field(..., ge=0, le=100)
    year: int
    month: int | None = None

    @field_validator("month")
    @classmethod
    def month_in_range(cls, v: int | None) -> int | None:
        if v is None:
            return v
        if not 1 <= v <= 12:
            raise ValueError("month must be between 1 and 12")
        return v

    @model_validator(mode="before")
    @classmethod
    def reject_none_or_empty(cls, data: Any) -> Any:
        return _reject_none_or_empty(data)


class TransportationMetric(BaseModel):
    model_config = ConfigDict(str_strip_whitespace=True, extra="forbid")

    metric_id: str = Field(..., min_length=1)
    source_status: SourceStatus = Field(
        ...,
        validation_alias=AliasChoices("source_status", "status"),
    )
    transit_ridership: int = Field(..., gt=0)
    bike_lane_km: float = Field(..., gt=0)
    year: int

    @model_validator(mode="before")
    @classmethod
    def reject_none_or_empty(cls, data: Any) -> Any:
        return _reject_none_or_empty(data)


class HealthcareMetric(BaseModel):
    model_config = ConfigDict(str_strip_whitespace=True, extra="forbid")

    metric_id: str = Field(..., min_length=1)
    source_status: SourceStatus = Field(
        ...,
        validation_alias=AliasChoices("source_status", "status"),
    )
    er_wait_hours: float = Field(..., gt=0)
    pct_no_family_doctor: float = Field(..., ge=0, le=100)
    year: int

    @model_validator(mode="before")
    @classmethod
    def reject_none_or_empty(cls, data: Any) -> Any:
        return _reject_none_or_empty(data)


class EmploymentMetric(BaseModel):
    model_config = ConfigDict(str_strip_whitespace=True, extra="forbid")

    metric_id: str = Field(..., min_length=1)
    source_status: SourceStatus = Field(
        ...,
        validation_alias=AliasChoices("source_status", "status"),
    )
    unemployment_rate: float = Field(..., ge=0, le=100)
    tech_jobs_total: int = Field(..., gt=0)
    year: int

    @model_validator(mode="before")
    @classmethod
    def reject_none_or_empty(cls, data: Any) -> Any:
        return _reject_none_or_empty(data)


def _reject_none_or_empty(data: Any) -> Any:
    if data is None:
        raise ValueError("Input cannot be None")
    if isinstance(data, dict):
        if len(data) == 0:
            raise ValueError("Input cannot be an empty dict")
        if all(v is None for v in data.values()):
            raise ValueError("Input cannot contain only None values")
    return data
