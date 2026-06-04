import json
from datetime import date
from pathlib import Path

from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import StaticPool

from app.api import routes
from app.core.database import Base, get_db
from app.main import app
from app.models.analysis import AnalysisJob, AnalysisResult, ComparisonJob, CoverageMetrics
from app.services.comparison import (
    aggregate_comparison_status,
    build_comparison_payload,
    build_comparison_table,
    comparison_warnings,
    safe_percent_change,
)


def _testing_session() -> tuple[sessionmaker[Session], object]:
    engine = create_engine(
        "sqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(bind=engine)
    return sessionmaker(bind=engine, autoflush=False, autocommit=False), engine


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


def _child(
    db: Session,
    *,
    analysis_id: str,
    year: int,
    status: str = "succeeded",
    ndvi: float = 0.3,
    ndwi: float = -0.2,
    ndbi: float = 0.1,
    normalized: float = 0.5,
    coverage: float = 1.0,
) -> None:
    db.add(
        AnalysisJob(
            id=analysis_id,
            zone_slug="rostov_on_don",
            zone_name="Ростов-на-Дону",
            geometry_geojson=json.dumps(_geometry(), ensure_ascii=False),
            year=year,
            date_start=date(year, 6, 1),
            date_end=date(year, 9, 15),
            status=status,
            progress=100 if status == "succeeded" else 20,
            stage="готово" if status == "succeeded" else "ошибка расчета",
            logs_json=json.dumps(["готово"], ensure_ascii=False),
            error_message=None if status == "succeeded" else "STAC недоступен",
        )
    )
    if status != "succeeded":
        return
    db.add(
        AnalysisResult(
            analysis_id=analysis_id,
            mean_ndvi=ndvi,
            mean_ndwi=ndwi,
            mean_ndbi=ndbi,
            median_ndvi=ndvi,
            median_ndwi=ndwi,
            median_ndbi=ndbi,
            valid_pixel_ratio=0.9,
            raw_score=normalized / 2,
            normalized_score=normalized,
            class_label="удовлетворительное",
            interpretation="Тестовая предварительная дистанционная оценка.",
        )
    )
    db.add(
        CoverageMetrics(
            analysis_id=analysis_id,
            zone_area_sq_km=120.0,
            raster_coverage_ratio=coverage,
            valid_pixel_ratio=0.9,
            masked_pixel_ratio=0.1,
            cloud_masked_pixel_ratio=0.02,
            nodata_pixel_ratio=0.01,
            selected_scene_intersects_zone=1,
            coverage_warning=None,
            method_note="Тестовая методика coverage.",
        )
    )


def test_safe_percent_change_handles_zero_baseline() -> None:
    assert safe_percent_change(0, 1) is None
    assert safe_percent_change(None, 1) is None
    assert safe_percent_change(2, 3) == 50


def test_comparison_table_contains_delta_and_percent_change() -> None:
    children = {
        "2020": {"stats": {"meanNDVI": 0.4, "normalizedScore": 0.5}},
        "2025": {"stats": {"meanNDVI": 0.2, "normalizedScore": 0.75}},
    }

    table = build_comparison_table(children)
    ndvi = next(row for row in table if row["metric"] == "meanNDVI")
    normalized = next(row for row in table if row["metric"] == "normalizedScore")

    assert ndvi["delta"] == -0.2
    assert ndvi["trend"] == "down"
    assert normalized["percentChange"] == 50


def test_partial_status_and_failed_child_warning() -> None:
    assert aggregate_comparison_status(["succeeded", "failed"]) == "partial"

    warnings = comparison_warnings(
        {
            "2020": {"status": "succeeded"},
            "2025": {"status": "failed", "errorMessage": "STAC недоступен"},
        }
    )

    assert warnings
    assert "2025" in warnings[0]


def test_coverage_difference_warning() -> None:
    warnings = comparison_warnings(
        {
            "2020": {"status": "succeeded", "coverage": {"rasterCoverageRatio": 1.0}},
            "2025": {"status": "succeeded", "coverage": {"rasterCoverageRatio": 0.5}},
        }
    )

    assert any("Покрытие зоны" in warning for warning in warnings)


def test_create_comparison_endpoint_creates_parent_and_children(monkeypatch) -> None:
    TestingSessionLocal, _ = _testing_session()

    dispatch_calls: list[tuple[str, float]] = []

    def fake_dispatch(comparison_id: str, cloud_cover_max: float) -> None:
        dispatch_calls.append((comparison_id, cloud_cover_max))

    monkeypatch.setattr(routes, "dispatch_comparison", fake_dispatch)

    def override_get_db():
        session = TestingSessionLocal()
        try:
            yield session
        finally:
            session.close()

    app.dependency_overrides[get_db] = override_get_db
    client = TestClient(app)
    try:
        response = client.post(
            "/api/comparisons",
            json={
                "zoneSlug": "rostov_on_don",
                "zoneName": "Ростов-на-Дону",
                "geometry": _geometry(),
                "years": [2020, 2025],
                "mode": "comparison",
                "cloudCoverMax": 20,
                "isCustomZone": False,
            },
        )
        assert response.status_code == 200, response.text
        body = response.json()
        assert body["comparisonId"]
        assert set(body["childAnalysisIds"]) == {"2020", "2025"}
        assert dispatch_calls == [(body["comparisonId"], 20)]

        db = TestingSessionLocal()
        try:
            comparison = db.get(ComparisonJob, body["comparisonId"])
            assert comparison is not None
            child_ids = json.loads(comparison.child_analysis_ids_json)
            assert db.get(AnalysisJob, child_ids["2020"]) is not None
            assert db.get(AnalysisJob, child_ids["2025"]) is not None
        finally:
            db.close()
    finally:
        app.dependency_overrides.clear()


def test_comparison_result_shape_includes_child_results(tmp_path: Path) -> None:
    TestingSessionLocal, _ = _testing_session()
    db = TestingSessionLocal()
    try:
        _child(db, analysis_id="a-2020", year=2020, ndvi=0.4, normalized=0.6)
        _child(db, analysis_id="a-2025", year=2025, ndvi=0.2, normalized=0.3, coverage=0.55)
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
        comparison.result_json = json.dumps(
            build_comparison_payload(db, comparison),
            ensure_ascii=False,
        )
        db.add(comparison)
        db.commit()
    finally:
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
        response = client.get("/api/comparisons/comparison-test/result")
        assert response.status_code == 200, response.text
        body = response.json()
        assert body["status"] == "succeeded"
        assert set(body["children"]) == {"2020", "2025"}
        assert body["children"]["2020"]["stats"]["meanNDVI"] == 0.4
        assert any(row["metric"] == "normalizedScore" for row in body["comparisonTable"])
        assert body["warnings"]
    finally:
        app.dependency_overrides.clear()
