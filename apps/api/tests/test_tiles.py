import warnings
from datetime import date
from pathlib import Path

import numpy as np
import rasterio
from fastapi.testclient import TestClient
from rasterio.errors import NotGeoreferencedWarning
from rasterio.transform import from_origin
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.core.database import Base, get_db
from app.main import app
from app.models.analysis import (
    AnalysisJob,
    AnalysisResult,
    CoverageMetrics,
    RasterAsset,
    SceneMetadata,
)
from app.services.colorize import colorize_index
from app.services.tiles import get_cached_or_rendered_tile_png


def test_colorizer_handles_nan_and_nodata() -> None:
    values = np.array([[0.1, np.nan], [-9999.0, 0.8]], dtype="float32")
    rgba = colorize_index("ndvi", values, nodata=-9999.0)
    assert rgba.shape == (2, 2, 4)
    assert rgba[0, 0, 3] == 255
    assert rgba[0, 1, 3] == 0
    assert rgba[1, 0, 3] == 0


def test_tile_endpoint_and_raster_metadata(tmp_path: Path) -> None:
    engine = create_engine(
        "sqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    TestingSessionLocal = sessionmaker(bind=engine, autoflush=False, autocommit=False)
    Base.metadata.create_all(bind=engine)

    raster_path = tmp_path / "ndvi.tif"
    with rasterio.open(
        raster_path,
        "w",
        driver="GTiff",
        height=16,
        width=16,
        count=1,
        dtype="float32",
        crs="EPSG:4326",
        transform=from_origin(0, 1, 0.05, 0.05),
        nodata=-9999.0,
    ) as dataset:
        dataset.write(np.full((16, 16), 0.35, dtype="float32"), 1)

    db = TestingSessionLocal()
    db.add(
        AnalysisJob(
            id="analysis-test",
            zone_slug="rostov_on_don",
            zone_name="Ростов-на-Дону",
            geometry_geojson="{}",
            year=2020,
            date_start=date(2020, 7, 1),
            date_end=date(2020, 8, 15),
            status="succeeded",
            progress=100,
            stage="готово",
        )
    )
    db.add(
        SceneMetadata(
            analysis_id="analysis-test",
            stac_item_id="S2B_T37TEN_20200719T081640_L2A",
            collection="sentinel-2-c1-l2a",
            datetime="2020-07-19T08:26:57.192000Z",
            cloud_cover=0.1,
            tile_id="37TEN",
            asset_urls_used="{}",
            reference_scene_id="S2B_37TEN_20200719_1_L2A",
            reference_scene_found=0,
            reference_note="Выбрана сцена, совпадающая с датой и тайлом дипломной reference-сцены.",
            thesis_reference_id="S2B_37TEN_20200719_1_L2A",
            reference_date="2020-07-19",
            reference_tile="37TEN",
            reference_match_status="same_date_tile",
            scene_selection_reason=(
                "Выбрана сцена, совпадающая с датой и тайлом дипломной reference-сцены."
            ),
            candidate_count=3,
            top_candidates_json="[]",
        )
    )
    db.add(
        AnalysisResult(
            analysis_id="analysis-test",
            mean_ndvi=0.35,
            mean_ndwi=-0.2,
            mean_ndbi=0.1,
            median_ndvi=0.35,
            median_ndwi=-0.2,
            median_ndbi=0.1,
            valid_pixel_ratio=1,
            raw_score=0.1,
            normalized_score=0.5,
            class_label="удовлетворительное",
            interpretation="Тестовая предварительная дистанционная оценка.",
        )
    )
    db.add(
        CoverageMetrics(
            analysis_id="analysis-test",
            zone_area_sq_km=100.0,
            raster_coverage_ratio=0.9,
            valid_pixel_ratio=0.75,
            masked_pixel_ratio=0.25,
            cloud_masked_pixel_ratio=0.1,
            nodata_pixel_ratio=0.05,
            selected_scene_intersects_zone=1,
            coverage_warning=None,
            method_note="Тестовая методика расчета coverage.",
        )
    )
    db.add(
        RasterAsset(
            analysis_id="analysis-test",
            layer="ndvi",
            path=str(raster_path),
            min=0.35,
            max=0.35,
            nodata=-9999.0,
            crs="EPSG:4326",
            bounds="[0, 0.2, 0.8, 1]",
        )
    )
    db.commit()
    db.close()

    def override_get_db():
        session = TestingSessionLocal()
        try:
            yield session
        finally:
            session.close()

    app.dependency_overrides[get_db] = override_get_db
    client = TestClient(app)
    try:
        tile = client.get("/api/tiles/analysis-test/ndvi/0/0/0.png")
        assert tile.status_code == 200, tile.text
        assert tile.headers["content-type"] == "image/png"
        assert tile.content.startswith(b"\x89PNG")

        invalid_layer = client.get("/api/tiles/analysis-test/bad/0/0/0.png")
        assert invalid_layer.status_code == 404

        missing_analysis = client.get("/api/tiles/missing/ndvi/0/0/0.png")
        assert missing_analysis.status_code == 404

        result = client.get("/api/analyses/analysis-test/result")
        assert result.status_code == 200
        layers = result.json()["rasterLayers"]
        assert layers[0]["layer"] == "ndvi"
        assert layers[0]["tileUrl"] == "/api/tiles/analysis-test/ndvi/{z}/{x}/{y}.png"
        coverage = result.json()["coverage"]
        assert coverage["rasterCoverageRatio"] == 0.9
        assert coverage["selectedSceneIntersectsZone"] is True
        scene = result.json()["scene"]
        assert scene["referenceMatchStatus"] == "same_date_tile"
        assert scene["sceneSelectionReason"].startswith("Выбрана сцена")
        assert scene["candidateCount"] == 3
    finally:
        app.dependency_overrides.clear()


def test_tile_cache_hit_and_miss(tmp_path: Path) -> None:
    raster_path = tmp_path / "ndvi.tif"
    with rasterio.open(
        raster_path,
        "w",
        driver="GTiff",
        height=16,
        width=16,
        count=1,
        dtype="float32",
        crs="EPSG:4326",
        transform=from_origin(0, 1, 0.05, 0.05),
        nodata=-9999.0,
    ) as dataset:
        dataset.write(np.full((16, 16), 0.35, dtype="float32"), 1)

    cache_dir = tmp_path / "cache"
    rendered = get_cached_or_rendered_tile_png(
        analysis_id="analysis-test",
        path=str(raster_path),
        layer="ndvi",
        z=0,
        x=0,
        y=0,
        nodata=-9999.0,
        cache_dir=cache_dir,
        cache_enabled=True,
    )
    cache_path = cache_dir / "analysis-test" / "ndvi" / "0" / "0" / "0.png"
    assert rendered.startswith(b"\x89PNG")
    assert cache_path.exists()

    cache_path.write_bytes(b"CACHED")
    cached = get_cached_or_rendered_tile_png(
        analysis_id="analysis-test",
        path=str(raster_path),
        layer="ndvi",
        z=0,
        x=0,
        y=0,
        nodata=-9999.0,
        cache_dir=cache_dir,
        cache_enabled=True,
    )
    assert cached == b"CACHED"


def test_tile_renderer_does_not_warn_for_georeferenced_raster(tmp_path: Path) -> None:
    raster_path = tmp_path / "ndvi.tif"
    with rasterio.open(
        raster_path,
        "w",
        driver="GTiff",
        height=16,
        width=16,
        count=1,
        dtype="float32",
        crs="EPSG:4326",
        transform=from_origin(39.5, 47.3, 0.01, 0.01),
        nodata=-9999.0,
    ) as dataset:
        dataset.write(np.full((16, 16), 0.35, dtype="float32"), 1)

    with warnings.catch_warnings(record=True) as caught:
        warnings.simplefilter("always")
        rendered = get_cached_or_rendered_tile_png(
            analysis_id="analysis-test",
            path=str(raster_path),
            layer="ndvi",
            z=8,
            x=156,
            y=89,
            nodata=-9999.0,
            cache_dir=tmp_path / "cache",
            cache_enabled=False,
        )

    assert rendered.startswith(b"\x89PNG")
    georef_warnings = [
        warning for warning in caught if issubclass(warning.category, NotGeoreferencedWarning)
    ]
    assert not georef_warnings
