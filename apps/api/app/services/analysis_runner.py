import json
from datetime import date
from pathlib import Path
from typing import Any

from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.core.database import SessionLocal
from app.models.analysis import AnalysisJob, AnalysisResult, RasterAsset, SceneMetadata
from app.services.zones import validate_geometry_area


def default_date_range(year: int) -> tuple[date, date]:
    return date(year, 6, 1), date(year, 9, 15)


def append_log(job: AnalysisJob, message: str) -> None:
    logs = json.loads(job.logs_json or "[]")
    logs.append(message)
    job.logs_json = json.dumps(logs, ensure_ascii=False)
    job.stage = message


def update_job(db: Session, job: AnalysisJob, *, status: str, progress: int, stage: str) -> None:
    job.status = status
    job.progress = progress
    append_log(job, stage)
    db.add(job)
    db.commit()
    db.refresh(job)


def persist_result_artifact(analysis_id: str, payload: dict[str, Any]) -> Path:
    settings = get_settings()
    path = settings.cache_dir / f"{analysis_id}-result.json"
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    return path


def run_analysis_job(analysis_id: str, cloud_cover_max: float) -> None:
    db = SessionLocal()
    try:
        job = db.get(AnalysisJob, analysis_id)
        if job is None:
            return

        geometry = json.loads(job.geometry_geojson)
        update_job(db, job, status="running", progress=5, stage="проверка геометрии зоны")
        validate_geometry_area(geometry)

        update_job(db, job, status="running", progress=12, stage="поиск сцен-кандидатов")
        from app.services.stac import resolve_assets, scene_metadata, search_best_scene

        item, candidates, reference_note = search_best_scene(
            zone_slug=job.zone_slug,
            geometry=geometry,
            start_date=job.date_start,
            end_date=job.date_end,
            cloud_cover_max=cloud_cover_max,
        )
        append_log(job, f"найдено кандидатов: {len(candidates)}")
        append_log(job, f"выбрана сцена: {item.id}")
        job.progress = 25
        db.add(job)
        db.commit()

        update_job(db, job, status="running", progress=30, stage="проверка покрытия зоны")
        assets = resolve_assets(item)
        append_log(job, "найдены assets: Red, Green, Blue, NIR, SWIR, SCL")
        db.add(job)
        db.commit()

        update_job(
            db,
            job,
            status="running",
            progress=42,
            stage="загрузка каналов Red, Green, Blue, NIR, SWIR, SCL",
        )
        update_job(
            db,
            job,
            status="running",
            progress=55,
            stage="приведение каналов к единой сетке",
        )
        update_job(
            db,
            job,
            status="running",
            progress=65,
            stage="маскирование облаков и невалидных пикселей",
        )
        update_job(db, job, status="running", progress=72, stage="расчет NDVI, NDWI, NDBI")
        from app.services.raster_outputs import save_raster_outputs
        from app.services.raster_reader import calculate_indices_from_assets

        calculation = calculate_indices_from_assets(assets, geometry)
        stats = calculation["stats"]

        update_job(db, job, status="running", progress=82, stage="расчет статистики")
        metadata = scene_metadata(item, assets, reference_note)

        db.merge(SceneMetadata(analysis_id=analysis_id, **_metadata_to_model(metadata)))
        db.merge(AnalysisResult(analysis_id=analysis_id, **stats))
        db.commit()

        update_job(db, job, status="running", progress=88, stage="сохранение растров")
        raster_assets = save_raster_outputs(
            analysis_id=analysis_id,
            rasters=calculation["rasters"],
            profile=calculation["profile"],
        )
        db.query(RasterAsset).filter(RasterAsset.analysis_id == analysis_id).delete()
        for raster_asset in raster_assets:
            db.add(raster_asset)
        db.commit()

        update_job(db, job, status="running", progress=92, stage="подготовка тайлов")
        persist_result_artifact(
            analysis_id,
            {
                "scene": metadata,
                "stats": stats,
                "rasterLayers": [_raster_to_artifact(asset) for asset in raster_assets],
            },
        )

        update_job(db, job, status="running", progress=96, stage="формирование интерпретации")
        update_job(db, job, status="succeeded", progress=100, stage="готово")
    except Exception as exc:  # noqa: BLE001
        job = db.get(AnalysisJob, analysis_id)
        if job is not None:
            job.status = "failed"
            job.error_message = str(exc)
            job.progress = max(job.progress, 1)
            append_log(job, f"ошибка: {exc}")
            db.add(job)
            db.commit()
    finally:
        db.close()


def _metadata_to_model(metadata: dict[str, Any]) -> dict[str, Any]:
    return {
        "stac_item_id": metadata["stac_item_id"],
        "collection": metadata["collection"],
        "datetime": metadata["datetime"],
        "cloud_cover": metadata["cloud_cover"],
        "tile_id": metadata["tile_id"],
        "asset_urls_used": json.dumps(metadata["asset_urls_used"], ensure_ascii=False),
        "reference_scene_id": metadata["reference_scene_id"],
        "reference_scene_found": metadata["reference_scene_found"],
        "reference_note": metadata["reference_note"],
    }


def _raster_to_artifact(asset: RasterAsset) -> dict[str, Any]:
    return {
        "layer": asset.layer,
        "path": asset.path,
        "min": asset.min,
        "max": asset.max,
        "nodata": asset.nodata,
        "crs": asset.crs,
        "bounds": json.loads(asset.bounds),
        "tileUrl": f"/api/tiles/{asset.analysis_id}/{asset.layer}/{{z}}/{{x}}/{{y}}.png",
    }
