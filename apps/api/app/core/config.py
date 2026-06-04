from functools import lru_cache
from pathlib import Path

from pydantic import AliasChoices, Field
from pydantic_settings import BaseSettings, SettingsConfigDict

PROJECT_ROOT = Path(__file__).resolve().parents[4]


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    project_name: str = "GeoEco Monitor"
    app_env: str = "development"
    job_execution_mode: str = "in_process"
    cors_allowed_origins: str = "http://localhost:3000,http://127.0.0.1:3000"
    database_url: str | None = None
    redis_url: str | None = None
    stac_url: str = Field(
        default="https://earth-search.aws.element84.com/v1",
        validation_alias=AliasChoices("STAC_URL", "STAC_API_URL"),
    )
    stac_collection: str = "sentinel-2-c1-l2a"
    data_dir: Path = Field(
        default=PROJECT_ROOT / "data",
        validation_alias=AliasChoices("DATA_DIR", "STORAGE_ROOT"),
    )
    raster_storage_dir: Path | None = None
    report_storage_dir: Path | None = None
    cache_storage_dir: Path | None = None
    max_zone_area_km2: float = Field(
        default=5000.0,
        validation_alias=AliasChoices("MAX_ZONE_AREA_KM2", "MAX_ZONE_AREA_SQ_KM"),
    )
    max_analysis_days: int = Field(
        default=140,
        validation_alias=AliasChoices("MAX_ANALYSIS_DAYS", "MAX_DATE_RANGE_DAYS"),
    )
    max_concurrent_jobs: int = Field(
        default=1,
        validation_alias=AliasChoices("MAX_CONCURRENT_JOBS", "MAX_CONCURRENT_ANALYSES"),
    )
    queue_name: str = "geoeco"
    queue_max_jobs: int = 20
    rq_default_timeout: int = 3600
    rq_analysis_timeout: int = 3600
    rq_comparison_timeout: int = 7200
    rq_report_timeout: int = 1200
    worker_concurrency: int = 1
    tile_cache_enabled: bool = True

    @property
    def cache_dir(self) -> Path:
        return self.cache_storage_dir or self.data_dir / "cache"

    @property
    def tile_cache_dir(self) -> Path:
        return self.cache_dir / "tiles"

    @property
    def rasters_dir(self) -> Path:
        return self.raster_storage_dir or self.data_dir / "rasters"

    @property
    def reports_dir(self) -> Path:
        return self.report_storage_dir or self.data_dir / "reports"

    @property
    def cors_origins(self) -> list[str]:
        return [
            origin.strip()
            for origin in self.cors_allowed_origins.split(",")
            if origin.strip()
        ]

    @property
    def effective_database_url(self) -> str:
        if self.database_url:
            return self.database_url
        return f"sqlite:///{(self.data_dir / 'geoeco.sqlite3').as_posix()}"


@lru_cache
def get_settings() -> Settings:
    settings = Settings()
    settings.cache_dir.mkdir(parents=True, exist_ok=True)
    settings.tile_cache_dir.mkdir(parents=True, exist_ok=True)
    settings.rasters_dir.mkdir(parents=True, exist_ok=True)
    settings.reports_dir.mkdir(parents=True, exist_ok=True)
    return settings
