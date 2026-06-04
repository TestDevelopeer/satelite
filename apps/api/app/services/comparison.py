import json
from typing import Any

from sqlalchemy.orm import Session

from app.core.database import SessionLocal
from app.models.analysis import (
    AnalysisJob,
    AnalysisResult,
    ComparisonJob,
    CoverageMetrics,
    RasterAsset,
    SceneMetadata,
)
from app.services.analysis_runner import run_analysis_job
from app.services.zones import find_reference

EPSILON = 1e-9


def append_comparison_log(comparison: ComparisonJob, message: str) -> None:
    logs = json.loads(comparison.logs_json or "[]")
    logs.append(message)
    comparison.logs_json = json.dumps(logs, ensure_ascii=False)
    comparison.stage = message


def update_comparison(
    db: Session,
    comparison: ComparisonJob,
    *,
    status: str,
    progress: int,
    stage: str,
) -> None:
    comparison.status = status
    comparison.progress = progress
    append_comparison_log(comparison, stage)
    db.add(comparison)
    db.commit()
    db.refresh(comparison)


def run_comparison_job(comparison_id: str, cloud_cover_max: float) -> None:
    db = SessionLocal()
    try:
        comparison = db.get(ComparisonJob, comparison_id)
        if comparison is None:
            return

        child_ids = json.loads(comparison.child_analysis_ids_json or "{}")
        years = json.loads(comparison.years_json)
        update_comparison(
            db,
            comparison,
            status="running",
            progress=5,
            stage="подготовка дочерних расчетов",
        )

        for index, year in enumerate(years):
            child_id = child_ids[str(year)]
            update_comparison(
                db,
                comparison,
                status="running",
                progress=10 + index * 40,
                stage=f"запуск дочернего расчета {year}",
            )
            run_analysis_job(child_id, cloud_cover_max)
            child = db.get(AnalysisJob, child_id)
            if child and child.status == "failed":
                append_comparison_log(comparison, f"дочерний расчет {year} завершился ошибкой")
            else:
                append_comparison_log(comparison, f"дочерний расчет {year} готов")
            db.add(comparison)
            db.commit()
            db.refresh(comparison)

        payload = build_comparison_payload(db, comparison)
        statuses = [payload["children"][str(year)]["status"] for year in years]
        final_status = aggregate_comparison_status(statuses)
        comparison.status = final_status
        comparison.progress = 100
        comparison.result_json = json.dumps(payload, ensure_ascii=False)
        final_stage = {
            "succeeded": "сравнение готово",
            "partial": "сравнение частично готово",
            "failed": "сравнение завершилось ошибкой",
        }.get(final_status, "сравнение завершено")
        append_comparison_log(comparison, final_stage)
        db.add(comparison)
        db.commit()
    except Exception as exc:  # noqa: BLE001
        comparison = db.get(ComparisonJob, comparison_id)
        if comparison is not None:
            comparison.status = "failed"
            comparison.error_message = str(exc)
            comparison.progress = max(comparison.progress, 1)
            append_comparison_log(comparison, f"ошибка сравнения: {exc}")
            db.add(comparison)
            db.commit()
    finally:
        db.close()


def aggregate_comparison_status(statuses: list[str]) -> str:
    if all(status == "succeeded" for status in statuses):
        return "succeeded"
    if any(status == "succeeded" for status in statuses):
        return "partial"
    if any(status in {"running", "queued"} for status in statuses):
        return "running"
    return "failed"


def build_comparison_payload(db: Session, comparison: ComparisonJob) -> dict[str, Any]:
    years = json.loads(comparison.years_json)
    child_ids = json.loads(comparison.child_analysis_ids_json or "{}")
    children = {
        str(year): child_result_to_response(db, child_ids[str(year)], year)
        for year in years
    }
    table = build_comparison_table(children)
    warnings = comparison_warnings(children)
    interpretation = build_comparison_interpretation(children, table, warnings)
    return {
        "comparisonId": comparison.id,
        "zoneSlug": comparison.zone_slug,
        "zoneName": comparison.zone_name,
        "years": years,
        "children": children,
        "comparisonTable": table,
        "warnings": warnings,
        "interpretation": interpretation,
        "referenceComparison": reference_comparison(comparison.zone_slug, years),
    }


def child_result_to_response(db: Session, analysis_id: str, year: int) -> dict[str, Any]:
    job = db.get(AnalysisJob, analysis_id)
    if job is None:
        return {
            "analysisId": analysis_id,
            "year": year,
            "status": "failed",
            "errorMessage": "Расчет не найден.",
        }

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
        "year": year,
        "status": job.status,
        "progress": job.progress,
        "stage": job.stage,
        "logs": json.loads(job.logs_json or "[]"),
        "errorMessage": job.error_message,
        "scene": scene_to_response(scene) if scene else None,
        "stats": stats_to_response(result) if result else None,
        "coverage": coverage_to_response(coverage) if coverage else None,
        "interpretation": result.interpretation if result else None,
        "rasterLayers": [raster_to_response(asset) for asset in raster_assets],
    }


def build_comparison_table(children: dict[str, dict[str, Any]]) -> list[dict[str, Any]]:
    return [
        comparison_row("meanNDVI", "NDVI", children, source="stats"),
        comparison_row("meanNDWI", "NDWI", children, source="stats"),
        comparison_row("meanNDBI", "NDBI", children, source="stats"),
        comparison_row("rawScore", "Raw score", children, source="stats"),
        comparison_row("normalizedScore", "Нормированная оценка", children, source="stats"),
        comparison_row("validPixelRatio", "Валидные пиксели", children, source="coverage"),
        comparison_row("rasterCoverageRatio", "Покрытие зоны", children, source="coverage"),
        class_change_row(children),
    ]


def comparison_row(
    metric: str,
    label: str,
    children: dict[str, dict[str, Any]],
    *,
    source: str,
) -> dict[str, Any]:
    value_2020 = metric_value(children, 2020, source, metric)
    value_2025 = metric_value(children, 2025, source, metric)
    delta = None if value_2020 is None or value_2025 is None else value_2025 - value_2020
    return {
        "metric": metric,
        "label": label,
        "value2020": value_2020,
        "value2025": value_2025,
        "delta": delta,
        "percentChange": safe_percent_change(value_2020, value_2025),
        "trend": trend_from_delta(delta),
    }


def class_change_row(children: dict[str, dict[str, Any]]) -> dict[str, Any]:
    class_2020 = (children.get("2020", {}).get("stats") or {}).get("classLabel")
    class_2025 = (children.get("2025", {}).get("stats") or {}).get("classLabel")
    return {
        "metric": "classLabel",
        "label": "Предварительный класс",
        "value2020": class_2020,
        "value2025": class_2025,
        "delta": None,
        "percentChange": None,
        "trend": "stable" if class_2020 == class_2025 and class_2020 else "changed",
    }


def metric_value(
    children: dict[str, dict[str, Any]],
    year: int,
    source: str,
    metric: str,
) -> float | None:
    value = (children.get(str(year), {}).get(source) or {}).get(metric)
    return float(value) if isinstance(value, int | float) and not isinstance(value, bool) else None


def safe_percent_change(baseline: float | None, current: float | None) -> float | None:
    if baseline is None or current is None or abs(baseline) < EPSILON:
        return None
    return ((current - baseline) / abs(baseline)) * 100


def trend_from_delta(delta: float | None, threshold: float = 0.005) -> str:
    if delta is None:
        return "unknown"
    if abs(delta) < threshold:
        return "stable"
    return "up" if delta > 0 else "down"


def comparison_warnings(children: dict[str, dict[str, Any]]) -> list[str]:
    warnings: list[str] = []
    failed = [
        f"{year}: {child.get('errorMessage')}"
        for year, child in children.items()
        if child.get("status") == "failed"
    ]
    if failed:
        warnings.append("Часть расчетов завершилась ошибкой: " + "; ".join(failed))

    coverage_2020 = metric_value(children, 2020, "coverage", "rasterCoverageRatio")
    coverage_2025 = metric_value(children, 2025, "coverage", "rasterCoverageRatio")
    if coverage_2020 is not None and coverage_2025 is not None:
        if abs(coverage_2025 - coverage_2020) > 0.2:
            warnings.append(
                "Покрытие зоны заметно отличается между годами, сравнение требует осторожности."
            )
    for year, child in children.items():
        coverage_warning = (child.get("coverage") or {}).get("coverageWarning")
        if coverage_warning:
            warnings.append(f"{year}: {coverage_warning}")
    return warnings


def build_comparison_interpretation(
    children: dict[str, dict[str, Any]],
    table: list[dict[str, Any]],
    warnings: list[str],
) -> str:
    succeeded = [year for year, child in children.items() if child.get("status") == "succeeded"]
    if len(succeeded) < 2:
        return (
            "Сравнение частично доступно: один из годов не был рассчитан. Доступные данные "
            "можно использовать как предварительный дистанционный сигнал, но выводы требуют "
            "повторного расчета второго года."
        )

    index_rows = [row for row in table if row["metric"] in {"meanNDVI", "meanNDWI", "meanNDBI"}]
    strongest = max(index_rows, key=lambda row: abs(row["delta"] or 0))
    norm = next(row for row in table if row["metric"] == "normalizedScore")
    class_row = next(row for row in table if row["metric"] == "classLabel")
    direction = "усилился" if (norm["delta"] or 0) > 0 else "снизился"
    if norm["trend"] == "stable":
        direction = "существенно не изменился"

    strongest_delta = strongest["delta"] if strongest["delta"] is not None else 0.0
    text = (
        f"Сравнение по спутниковым признакам показывает, что интегральный балл {direction}. "
        f"Наибольший вклад в изменение среди индексов дал показатель {strongest['label']} "
        f"(изменение {strongest_delta:.3f}). "
    )
    if class_row["trend"] == "changed":
        text += (
            f"Предварительный класс изменился: {class_row['value2020']} -> "
            f"{class_row['value2025']}. "
        )
    else:
        text += "Предварительный класс не изменился. "
    text += (
        "Это предварительный дистанционный сигнал и зона внимания; он требует уточнения "
        "натурными и лабораторными данными."
    )
    if warnings:
        text += " Сравнение следует трактовать осторожно из-за ограничений качества данных."
    return text


def reference_comparison(zone_slug: str, years: list[int]) -> dict[str, Any] | None:
    rows = [find_reference(zone_slug, year) for year in years]
    if not all(rows):
        return None
    assert rows[0] is not None and rows[1] is not None
    return {
        "title": "Значения дипломного reference-расчета",
        "note": (
            "Текущий live-расчет может отличаться из-за STAC ID, сцены, покрытия и версии "
            "обработки. Эти значения не подменяют live result."
        ),
        "rows": rows,
    }


def scene_to_response(scene: SceneMetadata) -> dict[str, Any]:
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


def stats_to_response(result: AnalysisResult) -> dict[str, Any]:
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


def coverage_to_response(coverage: CoverageMetrics) -> dict[str, Any]:
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


def raster_to_response(asset: RasterAsset) -> dict[str, Any]:
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
