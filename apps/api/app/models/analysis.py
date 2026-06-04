import uuid
from datetime import date, datetime

from sqlalchemy import Date, DateTime, Float, ForeignKey, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database import Base


def new_id() -> str:
    return str(uuid.uuid4())


class AnalysisJob(Base):
    __tablename__ = "analysis_jobs"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    zone_slug: Mapped[str] = mapped_column(String(80), nullable=False)
    zone_name: Mapped[str] = mapped_column(String(200), nullable=False)
    geometry_geojson: Mapped[str] = mapped_column(Text, nullable=False)
    is_custom_zone: Mapped[int] = mapped_column(Integer, default=0)
    year: Mapped[int] = mapped_column(Integer, nullable=False)
    date_start: Mapped[date] = mapped_column(Date, nullable=False)
    date_end: Mapped[date] = mapped_column(Date, nullable=False)
    status: Mapped[str] = mapped_column(String(40), default="queued")
    progress: Mapped[int] = mapped_column(Integer, default=0)
    stage: Mapped[str] = mapped_column(String(200), default="ожидание запуска")
    logs_json: Mapped[str] = mapped_column(Text, default="[]")
    error_message: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime, default=datetime.utcnow, onupdate=datetime.utcnow
    )


class ComparisonJob(Base):
    __tablename__ = "comparison_jobs"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    zone_slug: Mapped[str] = mapped_column(String(80), nullable=False)
    zone_name: Mapped[str] = mapped_column(String(200), nullable=False)
    geometry_geojson: Mapped[str] = mapped_column(Text, nullable=False)
    years_json: Mapped[str] = mapped_column(Text, nullable=False)
    child_analysis_ids_json: Mapped[str] = mapped_column(Text, default="{}")
    status: Mapped[str] = mapped_column(String(40), default="queued")
    progress: Mapped[int] = mapped_column(Integer, default=0)
    stage: Mapped[str] = mapped_column(String(200), default="ожидание запуска")
    logs_json: Mapped[str] = mapped_column(Text, default="[]")
    error_message: Mapped[str | None] = mapped_column(Text, nullable=True)
    result_json: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime, default=datetime.utcnow, onupdate=datetime.utcnow
    )


class SceneMetadata(Base):
    __tablename__ = "scene_metadata"

    analysis_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("analysis_jobs.id"), primary_key=True
    )
    stac_item_id: Mapped[str] = mapped_column(String(260), nullable=False)
    collection: Mapped[str] = mapped_column(String(120), nullable=False)
    datetime: Mapped[str] = mapped_column(String(80), nullable=False)
    cloud_cover: Mapped[float | None] = mapped_column(Float, nullable=True)
    tile_id: Mapped[str | None] = mapped_column(String(80), nullable=True)
    asset_urls_used: Mapped[str] = mapped_column(Text, default="{}")
    reference_scene_id: Mapped[str | None] = mapped_column(String(260), nullable=True)
    reference_scene_found: Mapped[int] = mapped_column(Integer, default=0)
    reference_note: Mapped[str | None] = mapped_column(Text, nullable=True)
    thesis_reference_id: Mapped[str | None] = mapped_column(String(260), nullable=True)
    reference_date: Mapped[str | None] = mapped_column(String(20), nullable=True)
    reference_tile: Mapped[str | None] = mapped_column(String(80), nullable=True)
    reference_match_status: Mapped[str | None] = mapped_column(String(40), nullable=True)
    scene_selection_reason: Mapped[str | None] = mapped_column(Text, nullable=True)
    candidate_count: Mapped[int | None] = mapped_column(Integer, nullable=True)
    top_candidates_json: Mapped[str | None] = mapped_column(Text, nullable=True)


class AnalysisResult(Base):
    __tablename__ = "analysis_results"

    analysis_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("analysis_jobs.id"), primary_key=True
    )
    mean_ndvi: Mapped[float] = mapped_column(Float)
    mean_ndwi: Mapped[float] = mapped_column(Float)
    mean_ndbi: Mapped[float] = mapped_column(Float)
    median_ndvi: Mapped[float] = mapped_column(Float)
    median_ndwi: Mapped[float] = mapped_column(Float)
    median_ndbi: Mapped[float] = mapped_column(Float)
    valid_pixel_ratio: Mapped[float] = mapped_column(Float)
    raw_score: Mapped[float] = mapped_column(Float)
    normalized_score: Mapped[float] = mapped_column(Float)
    class_label: Mapped[str] = mapped_column(String(40))
    interpretation: Mapped[str] = mapped_column(Text)


class CoverageMetrics(Base):
    __tablename__ = "coverage_metrics"

    analysis_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("analysis_jobs.id"), primary_key=True
    )
    zone_area_sq_km: Mapped[float] = mapped_column(Float)
    raster_coverage_ratio: Mapped[float] = mapped_column(Float)
    valid_pixel_ratio: Mapped[float] = mapped_column(Float)
    masked_pixel_ratio: Mapped[float] = mapped_column(Float)
    cloud_masked_pixel_ratio: Mapped[float] = mapped_column(Float)
    nodata_pixel_ratio: Mapped[float] = mapped_column(Float)
    selected_scene_intersects_zone: Mapped[int] = mapped_column(Integer)
    coverage_warning: Mapped[str | None] = mapped_column(Text, nullable=True)
    method_note: Mapped[str] = mapped_column(Text)


class RasterAsset(Base):
    __tablename__ = "raster_assets"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    analysis_id: Mapped[str] = mapped_column(String(36), ForeignKey("analysis_jobs.id"))
    layer: Mapped[str] = mapped_column(String(20), nullable=False)
    path: Mapped[str] = mapped_column(Text, nullable=False)
    min: Mapped[float | None] = mapped_column(Float, nullable=True)
    max: Mapped[float | None] = mapped_column(Float, nullable=True)
    nodata: Mapped[float | None] = mapped_column(Float, nullable=True)
    crs: Mapped[str] = mapped_column(String(100), nullable=False)
    bounds: Mapped[str] = mapped_column(Text, nullable=False)


class ReportJob(Base):
    __tablename__ = "report_jobs"

    id: Mapped[str] = mapped_column(String(120), primary_key=True)
    report_type: Mapped[str] = mapped_column(String(20), nullable=False)
    subject_id: Mapped[str] = mapped_column(String(36), nullable=False)
    status: Mapped[str] = mapped_column(String(40), default="pending")
    pdf_path: Mapped[str | None] = mapped_column(Text, nullable=True)
    html_path: Mapped[str | None] = mapped_column(Text, nullable=True)
    warnings_json: Mapped[str] = mapped_column(Text, default="[]")
    error_message: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime, default=datetime.utcnow, onupdate=datetime.utcnow
    )
