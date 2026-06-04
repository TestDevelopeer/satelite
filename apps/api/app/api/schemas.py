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


class ComparisonCreate(BaseModel):
    zone_slug: str = Field(alias="zoneSlug")
    zone_name: str = Field(alias="zoneName")
    geometry: dict[str, Any]
    years: list[int] = Field(default_factory=lambda: [2020, 2025], min_length=2, max_length=2)
    mode: Literal["comparison"] = "comparison"
    cloud_cover_max: float = Field(default=20, ge=0, le=100, alias="cloudCoverMax")
    is_custom_zone: bool = Field(default=False, alias="isCustomZone")


class ComparisonCreated(BaseModel):
    comparison_id: str = Field(alias="comparisonId")
    status: str
    child_analysis_ids: dict[str, str] = Field(alias="childAnalysisIds")


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


class ComparisonJobResponse(BaseModel):
    id: str
    zoneSlug: str
    zoneName: str
    years: list[int]
    status: str
    progress: int
    stage: str
    logs: list[str]
    errorMessage: str | None
    childAnalysisIds: dict[str, str]
    children: dict[str, dict[str, Any]]
    createdAt: str
    updatedAt: str


class ResultResponse(BaseModel):
    analysisId: str
    scene: dict[str, Any] | None
    stats: dict[str, Any] | None
    coverage: dict[str, Any] | None
    interpretation: str | None
    rasterLayers: list[dict[str, Any]] = []


class ComparisonResultResponse(BaseModel):
    comparisonId: str
    zoneSlug: str
    zoneName: str
    years: list[int]
    status: str
    children: dict[str, dict[str, Any]]
    comparisonTable: list[dict[str, Any]]
    warnings: list[str]
    interpretation: str
    referenceComparison: dict[str, Any] | None = None


class ReportCreated(BaseModel):
    reportType: Literal["analysis", "comparison"]
    id: str
    status: Literal["pending", "queued", "generating", "ready", "failed"]
    pdfUrl: str | None = None
    pdfPath: str | None = None
    htmlPath: str | None = None
    warnings: list[str] = []
    errorMessage: str | None = None
