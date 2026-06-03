from datetime import date
from pathlib import Path

import numpy as np
import rasterio
from fastapi.testclient import TestClient
from rasterio.transform import from_origin
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.core.database import Base, get_db
from app.main import app
from app.models.analysis import AnalysisJob, AnalysisResult, RasterAsset
from app.services.colorize import colorize_index


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
    finally:
        app.dependency_overrides.clear()
