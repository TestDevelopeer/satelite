from functools import lru_cache
from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict

PROJECT_ROOT = Path(__file__).resolve().parents[4]


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    project_name: str = "GeoEco Monitor"
    database_url: str | None = None
    stac_url: str = "https://earth-search.aws.element84.com/v1"
    stac_collection: str = "sentinel-2-c1-l2a"
    data_dir: Path = PROJECT_ROOT / "data"
    max_zone_area_km2: float = 5000.0
    max_analysis_days: int = 140
    max_concurrent_jobs: int = 1

    @property
    def cache_dir(self) -> Path:
        return self.data_dir / "cache"

    @property
    def rasters_dir(self) -> Path:
        return self.data_dir / "rasters"

    @property
    def effective_database_url(self) -> str:
        if self.database_url:
            return self.database_url
        return f"sqlite:///{(self.data_dir / 'geoeco.sqlite3').as_posix()}"


@lru_cache
def get_settings() -> Settings:
    settings = Settings()
    settings.cache_dir.mkdir(parents=True, exist_ok=True)
    settings.rasters_dir.mkdir(parents=True, exist_ok=True)
    return settings
