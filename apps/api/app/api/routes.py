import json
import re

from fastapi import APIRouter, Depends, HTTPException, Response
from fastapi.responses import FileResponse
from sqlalchemy.orm import Session

from app.api.schemas import (
    AnalysisCreate,
    AnalysisCreated,
    ComparisonCreate,
    ComparisonCreated,
    ComparisonJobResponse,
    ComparisonResultResponse,
    JobResponse,
    ReportCreated,
    ResultResponse,
)
from app.core.config import get_settings
from app.core.database import get_db
from app.models.analysis import (
    AnalysisJob,
    AnalysisResult,
    ComparisonJob,
    CoverageMetrics,
    RasterAsset,
    ReportJob,
    SceneMetadata,
)
from app.services.analysis_runner import default_date_range
from app.services.comparison import build_comparison_payload
from app.services.job_queue import (
    QueueOverloadedError,
    QueueUnavailableError,
    dispatch_analysis,
    dispatch_analysis_report,
    dispatch_comparison,
    dispatch_comparison_report,
)
from app.services.reports import (
    ReportError,
)
from app.services.tiles import get_cached_or_rendered_tile_png
from app.services.zones import load_default_zones, validate_geometry_area

router = APIRouter()
ALLOWED_TILE_LAYERS = {"rgb", "ndvi", "ndwi", "ndbi"}
SAFE_ID_PATTERN = re.compile(r"^[A-Za-z0-9_-]+$")


@router.get("/zones/defaults")
def default_zones() -> dict:
    return load_default_zones()


@router.post("/analyses", response_model=AnalysisCreated)
def create_analysis(
    payload: AnalysisCreate,
    db: Session = Depends(get_db),
) -> dict:
    if payload.mode != "single":
        raise HTTPException(status_code=400, detail="Phase 1 поддерживает только одиночный расчет.")

    try:
        validate_geometry_area(payload.geometry)
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc

    if payload.date_range:
        start = payload.date_range["start"]
        end = payload.date_range["end"]
    else:
        start, end = default_date_range(payload.year)

    if (end - start).days > get_settings().max_analysis_days:
        raise HTTPException(status_code=422, detail="Период анализа превышает допустимый лимит.")

    job = AnalysisJob(
        zone_slug=payload.zone_slug,
        zone_name=payload.zone_name,
        geometry_geojson=json.dumps(payload.geometry, ensure_ascii=False),
        is_custom_zone=int(payload.is_custom_zone),
        year=payload.year,
        date_start=start,
        date_end=end,
        status="queued",
        progress=0,
        stage="ожидание запуска",
        logs_json=json.dumps(["ожидание запуска"], ensure_ascii=False),
    )
    db.add(job)
    db.commit()
    db.refresh(job)

    try:
        dispatch_analysis(job.id, payload.cloud_cover_max)
    except QueueOverloadedError as exc:
        job.status = "failed"
        job.error_message = str(exc)
        db.add(job)
        db.commit()
        raise HTTPException(status_code=429, detail=str(exc)) from exc
    except QueueUnavailableError as exc:
        job.status = "failed"
        job.error_message = str(exc)
        db.add(job)
        db.commit()
        raise HTTPException(status_code=503, detail=str(exc)) from exc
    return {"analysisId": job.id, "status": job.status}


@router.get("/analyses/{analysis_id}", response_model=JobResponse)
def get_analysis(analysis_id: str, db: Session = Depends(get_db)) -> dict:
    job = db.get(AnalysisJob, analysis_id)
    if job is None:
        raise HTTPException(status_code=404, detail="Расчет не найден.")
    return _job_to_response(job)


@router.get("/analyses/{analysis_id}/result", response_model=ResultResponse)
def get_analysis_result(analysis_id: str, db: Session = Depends(get_db)) -> dict:
    job = db.get(AnalysisJob, analysis_id)
    if job is None:
        raise HTTPException(status_code=404, detail="Расчет не найден.")
    if job.status == "failed":
        detail = job.error_message or "Расчет завершился ошибкой."
        raise HTTPException(status_code=409, detail=detail)

    scene = db.get(SceneMetadata, analysis_id)
    result = db.get(AnalysisResult, analysis_id)
    coverage = db.get(CoverageMetrics, analysis_id)
    raster_assets = (
        db.query(RasterAsset)
        .filter(RasterAsset.analysis_id == analysis_id)
        .order_by(RasterAsset.layer)
        .all()
    )
    return {
        "analysisId": analysis_id,
        "scene": _scene_to_response(scene) if scene else None,
        "stats": _result_to_response(result) if result else None,
        "coverage": _coverage_to_response(coverage) if coverage else None,
        "interpretation": result.interpretation if result else None,
        "rasterLayers": [_raster_to_response(asset) for asset in raster_assets],
    }


@router.post("/comparisons", response_model=ComparisonCreated)
def create_comparison(
    payload: ComparisonCreate,
    db: Session = Depends(get_db),
) -> dict:
    years = payload.years
    if years != [2020, 2025]:
        raise HTTPException(
            status_code=400,
            detail="Phase 3 поддерживает только сравнение 2020 ↔ 2025.",
        )

    try:
        validate_geometry_area(payload.geometry)
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc

    child_ids: dict[str, str] = {}
    for year in years:
        start, end = default_date_range(year)
        if (end - start).days > get_settings().max_analysis_days:
            raise HTTPException(
                status_code=422,
                detail="Период анализа превышает допустимый лимит.",
            )
        child = AnalysisJob(
            zone_slug=payload.zone_slug,
            zone_name=payload.zone_name,
            geometry_geojson=json.dumps(payload.geometry, ensure_ascii=False),
            is_custom_zone=int(payload.is_custom_zone),
            year=year,
            date_start=start,
            date_end=end,
            status="queued",
            progress=0,
            stage="ожидание запуска",
            logs_json=json.dumps(["ожидание запуска"], ensure_ascii=False),
        )
        db.add(child)
        db.flush()
        child_ids[str(year)] = child.id

    comparison = ComparisonJob(
        zone_slug=payload.zone_slug,
        zone_name=payload.zone_name,
        geometry_geojson=json.dumps(payload.geometry, ensure_ascii=False),
        years_json=json.dumps(years),
        child_analysis_ids_json=json.dumps(child_ids),
        status="queued",
        progress=0,
        stage="ожидание запуска",
        logs_json=json.dumps(["ожидание запуска"], ensure_ascii=False),
    )
    db.add(comparison)
    db.commit()
    db.refresh(comparison)

    try:
        dispatch_comparison(comparison.id, payload.cloud_cover_max)
    except QueueOverloadedError as exc:
        comparison.status = "failed"
        comparison.error_message = str(exc)
        db.add(comparison)
        db.commit()
        raise HTTPException(status_code=429, detail=str(exc)) from exc
    except QueueUnavailableError as exc:
        comparison.status = "failed"
        comparison.error_message = str(exc)
        db.add(comparison)
        db.commit()
        raise HTTPException(status_code=503, detail=str(exc)) from exc
    return {
        "comparisonId": comparison.id,
        "status": comparison.status,
        "childAnalysisIds": child_ids,
    }


@router.get("/comparisons/{comparison_id}", response_model=ComparisonJobResponse)
def get_comparison(comparison_id: str, db: Session = Depends(get_db)) -> dict:
    comparison = db.get(ComparisonJob, comparison_id)
    if comparison is None:
        raise HTTPException(status_code=404, detail="Сравнение не найдено.")
    return _comparison_to_response(db, comparison)


@router.get("/comparisons/{comparison_id}/result", response_model=ComparisonResultResponse)
def get_comparison_result(comparison_id: str, db: Session = Depends(get_db)) -> dict:
    comparison = db.get(ComparisonJob, comparison_id)
    if comparison is None:
        raise HTTPException(status_code=404, detail="Сравнение не найдено.")
    if comparison.result_json:
        payload = json.loads(comparison.result_json)
    elif comparison.status in {"succeeded", "partial", "failed"}:
        payload = build_comparison_payload(db, comparison)
    else:
        raise HTTPException(status_code=409, detail="Сравнение еще не готово.")
    payload["status"] = comparison.status
    return payload


@router.post("/reports/analysis/{analysis_id}", response_model=ReportCreated)
def create_analysis_report(analysis_id: str, db: Session = Depends(get_db)) -> dict:
    _assert_analysis_report_ready(db, analysis_id)
    try:
        report = _create_or_reset_report_job(db, report_type="analysis", subject_id=analysis_id)
        dispatch_analysis_report(report.id, analysis_id)
    except ReportError as exc:
        raise HTTPException(status_code=exc.status_code, detail=exc.detail) from exc
    except QueueOverloadedError as exc:
        _mark_report_failed(db, "analysis", analysis_id, str(exc))
        raise HTTPException(status_code=429, detail=str(exc)) from exc
    except QueueUnavailableError as exc:
        _mark_report_failed(db, "analysis", analysis_id, str(exc))
        raise HTTPException(status_code=503, detail=str(exc)) from exc
    db.refresh(report)
    return _report_to_response(report)


@router.get("/reports/analysis/{analysis_id}/status", response_model=ReportCreated)
def get_analysis_report_status(analysis_id: str, db: Session = Depends(get_db)) -> dict:
    report = db.get(ReportJob, _report_job_id("analysis", analysis_id))
    if report is None:
        return {
            "reportType": "analysis",
            "id": analysis_id,
            "status": "pending",
            "warnings": [],
            "errorMessage": None,
        }
    return _report_to_response(report)


@router.post("/reports/comparison/{comparison_id}", response_model=ReportCreated)
def create_comparison_report(comparison_id: str, db: Session = Depends(get_db)) -> dict:
    _assert_comparison_report_ready(db, comparison_id)
    try:
        report = _create_or_reset_report_job(
            db, report_type="comparison", subject_id=comparison_id
        )
        dispatch_comparison_report(report.id, comparison_id)
    except ReportError as exc:
        raise HTTPException(status_code=exc.status_code, detail=exc.detail) from exc
    except QueueOverloadedError as exc:
        _mark_report_failed(db, "comparison", comparison_id, str(exc))
        raise HTTPException(status_code=429, detail=str(exc)) from exc
    except QueueUnavailableError as exc:
        _mark_report_failed(db, "comparison", comparison_id, str(exc))
        raise HTTPException(status_code=503, detail=str(exc)) from exc
    db.refresh(report)
    return _report_to_response(report)


@router.get("/reports/comparison/{comparison_id}/status", response_model=ReportCreated)
def get_comparison_report_status(comparison_id: str, db: Session = Depends(get_db)) -> dict:
    report = db.get(ReportJob, _report_job_id("comparison", comparison_id))
    if report is None:
        return {
            "reportType": "comparison",
            "id": comparison_id,
            "status": "pending",
            "warnings": [],
            "errorMessage": None,
        }
    return _report_to_response(report)


def _create_or_reset_report_job(db: Session, *, report_type: str, subject_id: str) -> ReportJob:
    report_id = _report_job_id(report_type, subject_id)
    report = db.get(ReportJob, report_id)
    if report is None:
        report = ReportJob(
            id=report_id,
            report_type=report_type,
            subject_id=subject_id,
            status="queued",
            warnings_json="[]",
        )
    else:
        report.status = "queued"
        report.error_message = None
        report.warnings_json = "[]"
    db.add(report)
    db.commit()
    db.refresh(report)
    return report


def _assert_analysis_report_ready(db: Session, analysis_id: str) -> None:
    job = db.get(AnalysisJob, analysis_id)
    if job is None:
        raise HTTPException(status_code=404, detail="Расчет не найден.")
    if job.status != "succeeded":
        raise HTTPException(
            status_code=409,
            detail="PDF можно сформировать только после успешного завершения расчета.",
        )


def _assert_comparison_report_ready(db: Session, comparison_id: str) -> None:
    comparison = db.get(ComparisonJob, comparison_id)
    if comparison is None:
        raise HTTPException(status_code=404, detail="Сравнение не найдено.")
    if comparison.status not in {"succeeded", "partial"}:
        raise HTTPException(
            status_code=409,
            detail="PDF можно сформировать только после завершения сравнения.",
        )


def _mark_report_failed(db: Session, report_type: str, subject_id: str, error: str) -> None:
    report = db.get(ReportJob, _report_job_id(report_type, subject_id))
    if report is None:
        return
    report.status = "failed"
    report.error_message = error
    db.add(report)
    db.commit()


def _report_job_id(report_type: str, subject_id: str) -> str:
    return f"{report_type}:{subject_id}"


def _report_to_response(report: ReportJob) -> dict:
    report_type = report.report_type
    subject_id = report.subject_id
    pdf_url = (
        f"/api/reports/{report_type}/{subject_id}.pdf"
        if report.status == "ready" and report.pdf_path
        else None
    )
    return {
        "reportType": report_type,
        "id": subject_id,
        "status": report.status,
        "pdfUrl": pdf_url,
        "pdfPath": report.pdf_path,
        "htmlPath": report.html_path,
        "warnings": json.loads(report.warnings_json or "[]"),
        "errorMessage": report.error_message,
    }


@router.get("/reports/analysis/{analysis_id}.pdf")
def download_analysis_report(analysis_id: str) -> FileResponse:
    _validate_safe_subject_id(analysis_id)
    path = get_settings().reports_dir / "analysis" / f"{analysis_id}.pdf"
    if not path.exists():
        raise HTTPException(status_code=404, detail="PDF-отчет еще не сформирован.")
    return FileResponse(
        path,
        media_type="application/pdf",
        filename=f"geoeco-analysis-{analysis_id}.pdf",
    )


@router.get("/reports/comparison/{comparison_id}.pdf")
def download_comparison_report(comparison_id: str) -> FileResponse:
    _validate_safe_subject_id(comparison_id)
    path = get_settings().reports_dir / "comparison" / f"{comparison_id}.pdf"
    if not path.exists():
        raise HTTPException(status_code=404, detail="PDF-отчет еще не сформирован.")
    return FileResponse(
        path,
        media_type="application/pdf",
        filename=f"geoeco-comparison-{comparison_id}.pdf",
    )


@router.get("/tiles/{analysis_id}/{layer}/{z}/{x}/{y_png}")
def get_tile(
    analysis_id: str,
    layer: str,
    z: int,
    x: int,
    y_png: str,
    db: Session = Depends(get_db),
) -> Response:
    if not y_png.endswith(".png"):
        raise HTTPException(status_code=404, detail="Тайл должен запрашиваться в формате PNG.")
    try:
        y = int(y_png.removesuffix(".png"))
    except ValueError as exc:
        raise HTTPException(status_code=404, detail="Некорректный номер тайла.") from exc

    job = db.get(AnalysisJob, analysis_id)
    if job is None:
        raise HTTPException(status_code=404, detail="Расчет не найден.")
    if job.status != "succeeded":
        raise HTTPException(status_code=409, detail="Растровые слои еще не готовы.")
    if layer not in ALLOWED_TILE_LAYERS:
        raise HTTPException(status_code=404, detail="Растровый слой не найден.")

    raster_asset = (
        db.query(RasterAsset)
        .filter(RasterAsset.analysis_id == analysis_id, RasterAsset.layer == layer)
        .first()
    )
    if raster_asset is None:
        raise HTTPException(status_code=404, detail="Растровый слой не найден.")

    try:
        settings = get_settings()
        tile = get_cached_or_rendered_tile_png(
            analysis_id=analysis_id,
            path=raster_asset.path,
            layer=layer,
            z=z,
            x=x,
            y=y,
            nodata=raster_asset.nodata,
            cache_dir=settings.tile_cache_dir,
            cache_enabled=settings.tile_cache_enabled,
        )
    except FileNotFoundError as exc:
        raise HTTPException(status_code=409, detail="Файл растрового слоя не найден.") from exc
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"Не удалось подготовить тайл: {exc}") from exc

    return Response(content=tile, media_type="image/png")


def _validate_safe_subject_id(subject_id: str) -> None:
    if not SAFE_ID_PATTERN.fullmatch(subject_id):
        raise HTTPException(status_code=404, detail="PDF-отчет не найден.")


def _job_to_response(job: AnalysisJob) -> dict:
    return {
        "id": job.id,
        "zoneSlug": job.zone_slug,
        "zoneName": job.zone_name,
        "year": job.year,
        "status": job.status,
        "progress": job.progress,
        "stage": job.stage,
        "logs": json.loads(job.logs_json or "[]"),
        "errorMessage": job.error_message,
        "createdAt": job.created_at.isoformat(),
        "updatedAt": job.updated_at.isoformat(),
    }


def _comparison_to_response(db: Session, comparison: ComparisonJob) -> dict:
    child_ids = json.loads(comparison.child_analysis_ids_json or "{}")
    children = {}
    for year, analysis_id in child_ids.items():
        child = db.get(AnalysisJob, analysis_id)
        if child is None:
            children[year] = {
                "analysisId": analysis_id,
                "year": int(year),
                "status": "failed",
                "progress": 0,
                "stage": "расчет не найден",
                "logs": [],
                "errorMessage": "Расчет не найден.",
            }
        else:
            children[year] = _job_to_response(child)
    return {
        "id": comparison.id,
        "zoneSlug": comparison.zone_slug,
        "zoneName": comparison.zone_name,
        "years": json.loads(comparison.years_json),
        "status": comparison.status,
        "progress": comparison.progress,
        "stage": comparison.stage,
        "logs": json.loads(comparison.logs_json or "[]"),
        "errorMessage": comparison.error_message,
        "childAnalysisIds": child_ids,
        "children": children,
        "createdAt": comparison.created_at.isoformat(),
        "updatedAt": comparison.updated_at.isoformat(),
    }


def _scene_to_response(scene: SceneMetadata) -> dict:
    return {
        "stacItemId": scene.stac_item_id,
        "collection": scene.collection,
        "datetime": scene.datetime,
        "cloudCover": scene.cloud_cover,
        "tileId": scene.tile_id,
        "assetUrlsUsed": json.loads(scene.asset_urls_used or "{}"),
        "referenceSceneId": scene.reference_scene_id,
        "referenceSceneFound": bool(scene.reference_scene_found),
        "referenceNote": scene.reference_note,
        "thesisReferenceId": scene.thesis_reference_id,
        "referenceDate": scene.reference_date,
        "referenceTile": scene.reference_tile,
        "referenceMatchStatus": scene.reference_match_status,
        "sceneSelectionReason": scene.scene_selection_reason,
        "candidateCount": scene.candidate_count,
        "topCandidates": json.loads(scene.top_candidates_json or "[]"),
    }


def _result_to_response(result: AnalysisResult) -> dict:
    return {
        "meanNDVI": result.mean_ndvi,
        "meanNDWI": result.mean_ndwi,
        "meanNDBI": result.mean_ndbi,
        "medianNDVI": result.median_ndvi,
        "medianNDWI": result.median_ndwi,
        "medianNDBI": result.median_ndbi,
        "validPixelRatio": result.valid_pixel_ratio,
        "rawScore": result.raw_score,
        "normalizedScore": result.normalized_score,
        "classLabel": result.class_label,
    }


def _coverage_to_response(coverage: CoverageMetrics) -> dict:
    return {
        "zoneAreaSqKm": coverage.zone_area_sq_km,
        "rasterCoverageRatio": coverage.raster_coverage_ratio,
        "validPixelRatio": coverage.valid_pixel_ratio,
        "maskedPixelRatio": coverage.masked_pixel_ratio,
        "cloudMaskedPixelRatio": coverage.cloud_masked_pixel_ratio,
        "nodataPixelRatio": coverage.nodata_pixel_ratio,
        "selectedSceneIntersectsZone": bool(coverage.selected_scene_intersects_zone),
        "coverageWarning": coverage.coverage_warning,
        "methodNote": coverage.method_note,
    }


def _raster_to_response(asset: RasterAsset) -> dict:
    return {
        "analysisId": asset.analysis_id,
        "layer": asset.layer,
        "path": asset.path,
        "min": asset.min,
        "max": asset.max,
        "nodata": asset.nodata,
        "crs": asset.crs,
        "bounds": json.loads(asset.bounds),
        "tileUrl": f"/api/tiles/{asset.analysis_id}/{asset.layer}/{{z}}/{{x}}/{{y}}.png",
    }
