from datetime import date
from typing import Any, Literal

from pydantic import BaseModel, Field


class AnalysisCreate(BaseModel):
    zone_slug: str = Field(alias="zoneSlug")
    zone_name: str = Field(alias="zoneName")
    geometry: dict[str, Any]
    year: int = Field(ge=2017, le=2026)
    date_range: dict[str, date] | None = Field(default=None, alias="dateRange")
    mode: Literal["single"] = "single"
    cloud_cover_max: float = Field(default=20, ge=0, le=100, alias="cloudCoverMax")
    is_custom_zone: bool = Field(default=False, alias="isCustomZone")


class AnalysisCreated(BaseModel):
    analysis_id: str = Field(alias="analysisId")
    status: str


class JobResponse(BaseModel):
    id: str
    zoneSlug: str
    zoneName: str
    year: int
    status: str
    progress: int
    stage: str
    logs: list[str]
    errorMessage: str | None
    createdAt: str
    updatedAt: str


class ResultResponse(BaseModel):
    analysisId: str
    scene: dict[str, Any] | None
    stats: dict[str, Any] | None
    interpretation: str | None
    rasterLayers: list[dict[str, Any]] = []
