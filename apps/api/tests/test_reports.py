import json
from datetime import date
from pathlib import Path

import numpy as np
import rasterio
from fastapi.testclient import TestClient
from rasterio.transform import from_origin
from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import StaticPool

from app.api import routes
from app.core.database import Base, get_db
from app.main import app
from app.models.analysis import (
    AnalysisJob,
    AnalysisResult,
    ComparisonJob,
    CoverageMetrics,
    RasterAsset,
    ReportJob,
    SceneMetadata,
)
from app.services import reports


class FakeSettings:
    def __init__(self, root: Path) -> None:
        self.reports_dir = root / "reports"


def _testing_session() -> sessionmaker[Session]:
    engine = create_engine(
        "sqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(bind=engine)
    return sessionmaker(bind=engine, autoflush=False, autocommit=False)


def _geometry() -> dict:
    return {
        "type": "Polygon",
        "coordinates": [
            [
                [39.58, 47.11],
                [39.82, 47.11],
                [39.82, 47.36],
                [39.58, 47.36],
                [39.58, 47.11],
            ]
        ],
    }


def _write_raster(path: Path, layer: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    profile = {
        "driver": "GTiff",
        "height": 16,
        "width": 16,
        "crs": "EPSG:4326",
        "transform": from_origin(39.5, 47.5, 0.01, 0.01),
    }
    if layer == "rgb":
        with rasterio.open(path, "w", count=4, dtype="uint8", **profile) as dataset:
            data = np.zeros((4, 16, 16), dtype="uint8")
            data[0] = 120
            data[1] = 150
            data[2] = 90
            data[3] = 255
            dataset.write(data)
    else:
        with rasterio.open(
            path, "w", count=1, dtype="float32", nodata=-9999.0, **profile
        ) as dataset:
            dataset.write(np.full((16, 16), 0.25, dtype="float32"), 1)


def _add_analysis(
    db: Session,
    tmp_path: Path,
    *,
    analysis_id: str,
    year: int,
    status: str = "succeeded",
) -> None:
    db.add(
        AnalysisJob(
            id=analysis_id,
            zone_slug="rostov_on_don",
            zone_name="Ростов-на-Дону",
            geometry_geojson=json.dumps(_geometry(), ensure_ascii=False),
            is_custom_zone=0,
            year=year,
            date_start=date(year, 6, 1),
            date_end=date(year, 9, 15),
            status=status,
            progress=100 if status == "succeeded" else 40,
            stage="готово" if status == "succeeded" else "расчет NDVI, NDWI, NDBI",
            logs_json=json.dumps(["готово"], ensure_ascii=False),
        )
    )
    if status != "succeeded":
        return
    db.add(
        SceneMetadata(
            analysis_id=analysis_id,
            stac_item_id=f"S2_TEST_{year}",
            collection="sentinel-2-c1-l2a",
            datetime=f"{year}-07-19T08:26:57Z",
            cloud_cover=0.1,
            tile_id="37TEN",
            asset_urls_used="{}",
            reference_scene_id=f"S2_REF_{year}",
            reference_scene_found=0,
            reference_note="Выбрана сцена, совпадающая с датой и тайлом.",
            thesis_reference_id=f"S2_REF_{year}",
            reference_date=f"{year}-07-19",
            reference_tile="37TEN",
            reference_match_status="same_date_tile",
            scene_selection_reason="Выбрана сцена, совпадающая с датой и тайлом.",
            candidate_count=2,
            top_candidates_json="[]",
        )
    )
    db.add(
        AnalysisResult(
            analysis_id=analysis_id,
            mean_ndvi=0.3,
            mean_ndwi=-0.2,
            mean_ndbi=0.05,
            median_ndvi=0.31,
            median_ndwi=-0.21,
            median_ndbi=0.04,
            valid_pixel_ratio=0.99,
            raw_score=0.1,
            normalized_score=0.5,
            class_label="удовлетворительное",
            interpretation="Тестовая предварительная дистанционная оценка.",
        )
    )
    db.add(
        CoverageMetrics(
            analysis_id=analysis_id,
            zone_area_sq_km=120.0,
            raster_coverage_ratio=0.98,
            valid_pixel_ratio=0.99,
            masked_pixel_ratio=0.01,
            cloud_masked_pixel_ratio=0.001,
            nodata_pixel_ratio=0.002,
            selected_scene_intersects_zone=1,
            coverage_warning=None,
            method_note="Тестовая методика coverage.",
        )
    )
    for layer in ["rgb", "ndvi", "ndwi", "ndbi"]:
        raster_path = tmp_path / analysis_id / f"{layer}.tif"
        _write_raster(raster_path, layer)
        db.add(
            RasterAsset(
                analysis_id=analysis_id,
                layer=layer,
                path=str(raster_path),
                min=0,
                max=1,
                nodata=None if layer == "rgb" else -9999.0,
                crs="EPSG:4326",
                bounds="[39.5, 47.3, 39.7, 47.5]",
            )
        )


def _client(
    TestingSessionLocal: sessionmaker[Session],
    tmp_path: Path,
    monkeypatch,
) -> TestClient:
    fake_settings = FakeSettings(tmp_path)
    monkeypatch.setattr(reports, "get_settings", lambda: fake_settings)
    monkeypatch.setattr(routes, "get_settings", lambda: fake_settings)

    def fake_render(html_path: Path, pdf_path: Path) -> None:
        assert html_path.exists()
        pdf_path.parent.mkdir(parents=True, exist_ok=True)
        pdf_path.write_bytes(b"%PDF-1.4\n1 0 obj<</Type/Catalog>>endobj\n%%EOF\n")

    monkeypatch.setattr(reports, "render_pdf_from_html", fake_render)

    def fake_analysis_dispatch(report_job_id: str, analysis_id: str) -> None:
        session = TestingSessionLocal()
        try:
            artifact = reports.ensure_analysis_report(session, analysis_id)
            report = session.get(ReportJob, report_job_id)
            assert report is not None
            report.status = "ready"
            report.pdf_path = str(artifact.pdf_path)
            report.html_path = str(artifact.html_path)
            report.warnings_json = json.dumps(artifact.warnings, ensure_ascii=False)
            session.add(report)
            session.commit()
        finally:
            session.close()

    def fake_comparison_dispatch(report_job_id: str, comparison_id: str) -> None:
        session = TestingSessionLocal()
        try:
            artifact = reports.ensure_comparison_report(session, comparison_id)
            report = session.get(ReportJob, report_job_id)
            assert report is not None
            report.status = "ready"
            report.pdf_path = str(artifact.pdf_path)
            report.html_path = str(artifact.html_path)
            report.warnings_json = json.dumps(artifact.warnings, ensure_ascii=False)
            session.add(report)
            session.commit()
        finally:
            session.close()

    monkeypatch.setattr(routes, "dispatch_analysis_report", fake_analysis_dispatch)
    monkeypatch.setattr(routes, "dispatch_comparison_report", fake_comparison_dispatch)

    def override_get_db():
        session = TestingSessionLocal()
        try:
            yield session
        finally:
            session.close()

    app.dependency_overrides[get_db] = override_get_db
    return TestClient(app)


def test_report_endpoint_rejects_missing_analysis(tmp_path: Path, monkeypatch) -> None:
    TestingSessionLocal = _testing_session()
    client = _client(TestingSessionLocal, tmp_path, monkeypatch)
    try:
        response = client.post("/api/reports/analysis/missing")
        assert response.status_code == 404
    finally:
        app.dependency_overrides.clear()


def test_report_download_rejects_unsafe_id() -> None:
    client = TestClient(app)
    response = client.get("/api/reports/analysis/bad.id.pdf")
    assert response.status_code == 404


def test_report_endpoint_rejects_unfinished_analysis(tmp_path: Path, monkeypatch) -> None:
    TestingSessionLocal = _testing_session()
    db = TestingSessionLocal()
    try:
        _add_analysis(db, tmp_path, analysis_id="analysis-running", year=2020, status="running")
        db.commit()
    finally:
        db.close()

    client = _client(TestingSessionLocal, tmp_path, monkeypatch)
    try:
        response = client.post("/api/reports/analysis/analysis-running")
        assert response.status_code == 409
    finally:
        app.dependency_overrides.clear()


def test_single_analysis_report_creates_pdf_file(tmp_path: Path, monkeypatch) -> None:
    TestingSessionLocal = _testing_session()
    db = TestingSessionLocal()
    try:
        _add_analysis(db, tmp_path, analysis_id="analysis-test", year=2020)
        db.commit()
    finally:
        db.close()

    client = _client(TestingSessionLocal, tmp_path, monkeypatch)
    try:
        response = client.post("/api/reports/analysis/analysis-test")
        assert response.status_code == 200, response.text
        body = response.json()
        assert body["pdfUrl"] == "/api/reports/analysis/analysis-test.pdf"
        pdf_path = Path(body["pdfPath"])
        assert pdf_path.exists()
        assert pdf_path.stat().st_size > 0
        assert "data/reports" not in str(pdf_path)

        download = client.get(body["pdfUrl"])
        assert download.status_code == 200
        assert download.headers["content-type"] == "application/pdf"
    finally:
        app.dependency_overrides.clear()


def test_comparison_report_creates_pdf_file(tmp_path: Path, monkeypatch) -> None:
    TestingSessionLocal = _testing_session()
    db = TestingSessionLocal()
    try:
        _add_analysis(db, tmp_path, analysis_id="a-2020", year=2020)
        _add_analysis(db, tmp_path, analysis_id="a-2025", year=2025)
        comparison = ComparisonJob(
            id="comparison-test",
            zone_slug="rostov_on_don",
            zone_name="Ростов-на-Дону",
            geometry_geojson=json.dumps(_geometry(), ensure_ascii=False),
            years_json=json.dumps([2020, 2025]),
            child_analysis_ids_json=json.dumps({"2020": "a-2020", "2025": "a-2025"}),
            status="succeeded",
            progress=100,
            stage="готово",
            logs_json=json.dumps(["готово"], ensure_ascii=False),
        )
        db.add(comparison)
        db.commit()
    finally:
        db.close()

    client = _client(TestingSessionLocal, tmp_path, monkeypatch)
    try:
        response = client.post("/api/reports/comparison/comparison-test")
        assert response.status_code == 200, response.text
        body = response.json()
        assert body["pdfUrl"] == "/api/reports/comparison/comparison-test.pdf"
        assert Path(body["pdfPath"]).exists()
        assert Path(body["htmlPath"]).exists()
        assert Path(body["pdfPath"]).stat().st_size > 0
    finally:
        app.dependency_overrides.clear()


def test_report_endpoint_rejects_unfinished_comparison(tmp_path: Path, monkeypatch) -> None:
    TestingSessionLocal = _testing_session()
    db = TestingSessionLocal()
    try:
        db.add(
            ComparisonJob(
                id="comparison-running",
                zone_slug="rostov_on_don",
                zone_name="Ростов-на-Дону",
                geometry_geojson=json.dumps(_geometry(), ensure_ascii=False),
                years_json=json.dumps([2020, 2025]),
                child_analysis_ids_json="{}",
                status="running",
                progress=50,
                stage="запуск дочернего расчета 2025",
                logs_json="[]",
            )
        )
        db.commit()
    finally:
        db.close()

    client = _client(TestingSessionLocal, tmp_path, monkeypatch)
    try:
        response = client.post("/api/reports/comparison/comparison-running")
        assert response.status_code == 409
    finally:
        app.dependency_overrides.clear()


def test_preview_generation_handles_missing_raster_gracefully(tmp_path: Path) -> None:
    warnings: list[str] = []
    previews = reports.build_preview_set(
        [
            {
                "analysisId": "analysis-test",
                "layer": "ndvi",
                "path": str(tmp_path / "missing.tif"),
                "nodata": -9999.0,
            }
        ],
        tmp_path / "assets",
        ["ndvi"],
        warnings,
    )

    assert previews["ndvi"] is None
    assert warnings
    assert "Preview NDVI" in warnings[0]
