import json
from concurrent.futures import ThreadPoolExecutor

from fastapi import APIRouter, Depends, HTTPException, Response
from sqlalchemy.orm import Session

from app.api.schemas import AnalysisCreate, AnalysisCreated, JobResponse, ResultResponse
from app.core.config import get_settings
from app.core.database import get_db
from app.models.analysis import AnalysisJob, AnalysisResult, RasterAsset, SceneMetadata
from app.services.analysis_runner import default_date_range, run_analysis_job
from app.services.tiles import render_tile_png
from app.services.zones import load_default_zones, validate_geometry_area

router = APIRouter()
executor = ThreadPoolExecutor(max_workers=get_settings().max_concurrent_jobs)
ALLOWED_TILE_LAYERS = {"rgb", "ndvi", "ndwi", "ndbi"}


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

    executor.submit(run_analysis_job, job.id, payload.cloud_cover_max)
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
        "interpretation": result.interpretation if result else None,
        "rasterLayers": [_raster_to_response(asset) for asset in raster_assets],
    }


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
        tile = render_tile_png(raster_asset.path, layer, z, x, y, raster_asset.nodata)
    except FileNotFoundError as exc:
        raise HTTPException(status_code=409, detail="Файл растрового слоя не найден.") from exc
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"Не удалось подготовить тайл: {exc}") from exc

    return Response(content=tile, media_type="image/png")


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
