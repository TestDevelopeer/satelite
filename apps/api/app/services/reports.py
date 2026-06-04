import base64
import html
import json
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Any

import numpy as np
import rasterio
from PIL import Image
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.models.analysis import (
    AnalysisJob,
    AnalysisResult,
    ComparisonJob,
    CoverageMetrics,
    RasterAsset,
    SceneMetadata,
)
from app.services.colorize import colorize_index, rgba_from_rgb_bands
from app.services.comparison import build_comparison_payload
from app.services.zones import load_default_zones

DISCLAIMER = (
    "Результат является предварительной дистанционной оценкой по спутниковым данным "
    "Sentinel-2 и не заменяет лабораторные измерения, санитарно-гигиеническую "
    "экспертизу и натурное обследование."
)

METHOD_LIMITS = [
    (
        "Спутниковые индексы отражают спектральные признаки поверхности, "
        "а не прямые лабораторные показатели загрязнения."
    ),
    (
        "На результат влияют дата съемки, сезонность, облачность, тени, "
        "качество SCL-маски и покрытие зоны сценой."
    ),
    (
        "Сравнение разных лет требует осторожной интерпретации, потому что сцены "
        "могут отличаться по дате, углу съемки и атмосферным условиям."
    ),
    (
        "Итоговый класс является предварительной дистанционной оценкой и требует "
        "проверки натурными и лабораторными данными."
    ),
]

FORMULAS = [
    "NDVI = (NIR - Red) / (NIR + Red)",
    "NDWI = (Green - NIR) / (Green + NIR)",
    "NDBI = (SWIR - NIR) / (SWIR + NIR)",
]


class ReportError(RuntimeError):
    def __init__(self, status_code: int, detail: str) -> None:
        super().__init__(detail)
        self.status_code = status_code
        self.detail = detail


@dataclass(frozen=True)
class ReportArtifact:
    pdf_path: Path
    html_path: Path
    download_url: str
    warnings: list[str]


def ensure_analysis_report(db: Session, analysis_id: str) -> ReportArtifact:
    job = _get_finished_analysis(db, analysis_id)
    settings = get_settings()
    pdf_path = settings.reports_dir / "analysis" / f"{analysis_id}.pdf"
    html_path = settings.reports_dir / "html" / "analysis" / f"{analysis_id}.html"
    if _is_existing_report_current(pdf_path, job.updated_at):
        return ReportArtifact(
            pdf_path=pdf_path,
            html_path=html_path,
            download_url=f"/api/reports/analysis/{analysis_id}.pdf",
            warnings=[],
        )

    payload = build_analysis_report_payload(db, job)
    warnings: list[str] = []
    previews = build_preview_set(
        payload["rasterLayers"],
        settings.reports_dir / "assets" / "analysis" / analysis_id,
        ["rgb", "ndvi", "ndwi", "ndbi"],
        warnings,
    )
    html_text = render_single_analysis_html(payload, previews, warnings)
    _write_text(html_path, html_text)
    render_pdf_from_html(html_path, pdf_path)
    return ReportArtifact(
        pdf_path=pdf_path,
        html_path=html_path,
        download_url=f"/api/reports/analysis/{analysis_id}.pdf",
        warnings=warnings,
    )


def ensure_comparison_report(db: Session, comparison_id: str) -> ReportArtifact:
    comparison = db.get(ComparisonJob, comparison_id)
    if comparison is None:
        raise ReportError(404, "Сравнение не найдено.")
    if comparison.status not in {"succeeded", "partial"}:
        raise ReportError(409, "PDF можно сформировать только после завершения сравнения.")

    settings = get_settings()
    pdf_path = settings.reports_dir / "comparison" / f"{comparison_id}.pdf"
    html_path = settings.reports_dir / "html" / "comparison" / f"{comparison_id}.html"
    if _is_existing_report_current(pdf_path, comparison.updated_at):
        return ReportArtifact(
            pdf_path=pdf_path,
            html_path=html_path,
            download_url=f"/api/reports/comparison/{comparison_id}.pdf",
            warnings=[],
        )

    payload = (
        json.loads(comparison.result_json)
        if comparison.result_json
        else build_comparison_payload(db, comparison)
    )
    payload["status"] = comparison.status
    payload["parent"] = {
        "comparisonId": comparison.id,
        "childAnalysisIds": json.loads(comparison.child_analysis_ids_json or "{}"),
        "status": comparison.status,
        "zoneSlug": comparison.zone_slug,
        "zoneName": comparison.zone_name,
        "geometry": json.loads(comparison.geometry_geojson),
    }
    payload["zoneInfo"] = zone_info(
        comparison.zone_slug,
        comparison.zone_name,
        json.loads(comparison.geometry_geojson),
        is_custom=0,
    )

    warnings: list[str] = []
    previews_by_year: dict[str, dict[str, str | None]] = {}
    for year, child in payload["children"].items():
        previews_by_year[year] = build_preview_set(
            child.get("rasterLayers") or [],
            settings.reports_dir / "assets" / "comparison" / comparison_id / str(year),
            ["rgb", "ndvi", "ndbi", "ndwi"],
            warnings,
        )

    html_text = render_comparison_html(payload, previews_by_year, warnings)
    _write_text(html_path, html_text)
    render_pdf_from_html(html_path, pdf_path)
    return ReportArtifact(
        pdf_path=pdf_path,
        html_path=html_path,
        download_url=f"/api/reports/comparison/{comparison_id}.pdf",
        warnings=warnings,
    )


def build_analysis_report_payload(db: Session, job: AnalysisJob) -> dict[str, Any]:
    scene = db.get(SceneMetadata, job.id)
    result = db.get(AnalysisResult, job.id)
    coverage = db.get(CoverageMetrics, job.id)
    raster_assets = (
        db.query(RasterAsset)
        .filter(RasterAsset.analysis_id == job.id)
        .order_by(RasterAsset.layer)
        .all()
    )
    if scene is None or result is None or coverage is None:
        raise ReportError(
            409, "Результат расчета неполный: нет метаданных сцены, статистики или coverage."
        )
    return {
        "analysisId": job.id,
        "job": {
            "id": job.id,
            "zoneSlug": job.zone_slug,
            "zoneName": job.zone_name,
            "year": job.year,
            "dateStart": job.date_start.isoformat(),
            "dateEnd": job.date_end.isoformat(),
            "status": job.status,
        },
        "zoneInfo": zone_info(
            job.zone_slug,
            job.zone_name,
            json.loads(job.geometry_geojson),
            is_custom=job.is_custom_zone,
        ),
        "scene": scene_to_dict(scene),
        "stats": stats_to_dict(result),
        "coverage": coverage_to_dict(coverage),
        "interpretation": result.interpretation,
        "rasterLayers": [raster_to_dict(asset) for asset in raster_assets],
    }


def build_preview_set(
    raster_layers: list[dict[str, Any]],
    output_dir: Path,
    layers: list[str],
    warnings: list[str],
) -> dict[str, str | None]:
    by_layer = {asset["layer"]: asset for asset in raster_layers}
    previews: dict[str, str | None] = {}
    for layer in layers:
        asset = by_layer.get(layer)
        if asset is None:
            previews[layer] = None
            warnings.append(f"Preview {layer.upper()} не создан: raster asset отсутствует.")
            continue
        try:
            preview_path = output_dir / f"{layer}.png"
            previews[layer] = create_raster_preview(asset, preview_path)
        except Exception as exc:  # noqa: BLE001
            previews[layer] = None
            warnings.append(f"Preview {layer.upper()} не создан: {exc}")
    return previews


def create_raster_preview(asset: dict[str, Any], output_path: Path) -> str:
    raster_path = Path(asset["path"])
    if not raster_path.exists():
        raise FileNotFoundError(f"файл слоя не найден: {raster_path}")

    output_path.parent.mkdir(parents=True, exist_ok=True)
    with rasterio.open(raster_path) as dataset:
        width, height = _preview_size(dataset.width, dataset.height)
        if asset["layer"] == "rgb":
            band_count = min(dataset.count, 4)
            data = dataset.read(
                indexes=list(range(1, band_count + 1)),
                out_shape=(band_count, height, width),
            )
            rgba = rgba_from_rgb_bands(data)
        else:
            data = dataset.read(1, out_shape=(height, width)).astype("float32")
            rgba = colorize_index(asset["layer"], data, nodata=asset.get("nodata"))

    image = Image.fromarray(rgba, "RGBA")
    image.save(output_path, "PNG", optimize=True)
    return _data_uri(output_path)


def render_pdf_from_html(html_path: Path, pdf_path: Path) -> None:
    try:
        from playwright.sync_api import Error as PlaywrightError
        from playwright.sync_api import sync_playwright
    except ImportError as exc:
        raise ReportError(
            500,
            "Playwright не установлен в backend venv. Выполните: "
            "apps\\api\\.venv\\Scripts\\python.exe -m pip install -r apps/api/requirements.txt",
        ) from exc

    pdf_path.parent.mkdir(parents=True, exist_ok=True)
    try:
        with sync_playwright() as playwright:
            browser = playwright.chromium.launch(args=["--no-sandbox"])
            page = browser.new_page(viewport={"width": 1240, "height": 1754})
            page.goto(html_path.resolve().as_uri(), wait_until="networkidle")
            page.pdf(
                path=str(pdf_path),
                format="A4",
                print_background=True,
                margin={"top": "14mm", "right": "14mm", "bottom": "14mm", "left": "14mm"},
            )
            browser.close()
    except PlaywrightError as exc:
        message = str(exc)
        if "Executable doesn't exist" in message or "playwright install" in message:
            raise ReportError(
                500,
                "Chromium для Playwright не установлен. Выполните: "
                "apps\\api\\.venv\\Scripts\\python.exe -m playwright install chromium",
            ) from exc
        raise ReportError(500, f"Не удалось сформировать PDF через Chromium: {exc}") from exc


def render_single_analysis_html(
    payload: dict[str, Any],
    previews: dict[str, str | None],
    warnings: list[str],
) -> str:
    job = payload["job"]
    zone = payload["zoneInfo"]
    scene = payload["scene"]
    stats = payload["stats"]
    coverage = payload["coverage"]
    reference_date_tile = f'{scene["referenceDate"] or "—"} / {scene["referenceTile"] or "—"}'
    return page(
        title="Предварительная дистанционная оценка территории",
        body=f"""
        <section class="hero">
          <div>
            <div class="eyebrow">GeoEco Monitor</div>
            <h1>Предварительная дистанционная оценка территории</h1>
            <p>{e(zone["name"])} · {e(str(job["year"]))}</p>
          </div>
          <div class="stamp">Sentinel-2 L2A<br>{e(generated_at())}</div>
        </section>
        {section("Зона и период", definition_table([
            ("Название", zone["name"]),
            ("Slug", zone["slug"]),
            ("Тип зоны", zone["zoneType"]),
            ("Геометрия", zone["geometryType"]),
            ("Источник границы", zone["boundarySource"]),
            ("BBox", zone["bboxText"]),
            ("Площадь зоны", f'{fmt(coverage["zoneAreaSqKm"], 1)} км²'),
            ("Период", f'{job["dateStart"]} - {job["dateEnd"]}'),
        ]))}
        {section("Сцена Sentinel-2", definition_table([
            ("STAC item ID", scene["stacItemId"]),
            ("Collection", scene["collection"]),
            ("Дата и время", scene["datetime"]),
            ("Облачность", pct_from_percent(scene["cloudCover"])),
            ("MGRS tile", scene["tileId"]),
            ("Reference date/tile", reference_date_tile),
            ("Reference match status", scene["referenceMatchStatus"]),
            ("Причина выбора", scene["sceneSelectionReason"]),
        ]))}
        {section("Качество данных", definition_table([
            ("Покрытие зоны", pct(coverage["rasterCoverageRatio"])),
            ("Валидные пиксели", pct(coverage["validPixelRatio"])),
            ("Маскированные пиксели", pct(coverage["maskedPixelRatio"])),
            ("Облака/тени по SCL", pct(coverage["cloudMaskedPixelRatio"])),
            ("Nodata", pct(coverage["nodataPixelRatio"])),
            ("Coverage warning", coverage["coverageWarning"] or "Критичных предупреждений нет"),
            ("Method note", coverage["methodNote"]),
        ]))}
        {section("Индексы и итоговый класс", metric_grid([
            ("Mean NDVI", fmt(stats["meanNDVI"])),
            ("Mean NDWI", fmt(stats["meanNDWI"])),
            ("Mean NDBI", fmt(stats["meanNDBI"])),
            ("Median NDVI", fmt(stats["medianNDVI"])),
            ("Median NDWI", fmt(stats["medianNDWI"])),
            ("Median NDBI", fmt(stats["medianNDBI"])),
            ("Raw score", fmt(stats["rawScore"], 4)),
            ("Normalized score", fmt(stats["normalizedScore"])),
            ("Итоговый класс", stats["classLabel"]),
        ]))}
        {preview_section("Raster previews", [
            ("RGB preview", previews.get("rgb")),
            ("NDVI preview", previews.get("ndvi")),
            ("NDWI preview", previews.get("ndwi")),
            ("NDBI preview", previews.get("ndbi")),
        ])}
        {section("Интерпретация", paragraph(payload["interpretation"]))}
        {section("Формулы", bullet_list(FORMULAS))}
        {section("Ограничения метода", bullet_list(METHOD_LIMITS + warnings))}
        {disclaimer()}
        """,
    )


def render_comparison_html(
    payload: dict[str, Any],
    previews_by_year: dict[str, dict[str, str | None]],
    warnings: list[str],
) -> str:
    zone = payload["zoneInfo"]
    parent = payload["parent"]
    scene_rows = [
        [
            year,
            (child.get("scene") or {}).get("stacItemId"),
            (child.get("scene") or {}).get("datetime"),
            (child.get("scene") or {}).get("tileId"),
            pct_from_percent((child.get("scene") or {}).get("cloudCover")),
            (child.get("scene") or {}).get("referenceMatchStatus"),
            pct((child.get("coverage") or {}).get("rasterCoverageRatio")),
            pct((child.get("coverage") or {}).get("validPixelRatio")),
        ]
        for year, child in payload["children"].items()
    ]
    comparison_rows = [
        [
            row["label"],
            cell(row["value2020"], row["metric"]),
            cell(row["value2025"], row["metric"]),
            fmt(row["delta"]) if isinstance(row["delta"], int | float) else "—",
            f'{row["percentChange"]:.1f}%'
            if isinstance(row["percentChange"], int | float)
            else "—",
            trend_label(row["trend"]),
        ]
        for row in payload["comparisonTable"]
    ]
    scene_headers = [
        "Год",
        "STAC item ID",
        "Дата",
        "Tile",
        "Cloud",
        "Reference match",
        "Coverage",
        "Valid pixels",
    ]
    comparison_limits = METHOD_LIMITS + payload.get("warnings", []) + warnings
    reference_block = ""
    if payload.get("referenceComparison"):
        reference = payload["referenceComparison"]
        reference_rows = [
            [
                row.get("year"),
                fmt(row.get("NDVI")),
                fmt(row.get("NDWI")),
                fmt(row.get("NDBI")),
                fmt(row.get("rawScore"), 4),
                fmt(row.get("normalized")),
                row.get("class"),
                row.get("sceneId"),
                row.get("sceneDate"),
            ]
            for row in reference.get("rows", [])
        ]
        reference_block = section(
            reference["title"],
            f"<p>{e(reference['note'])}</p>"
            + simple_table(
                ["Год", "NDVI", "NDWI", "NDBI", "Raw", "Norm", "Класс", "Scene ID", "Дата"],
                reference_rows,
            ),
        )

    return page(
        title="Сравнение предварительной дистанционной оценки 2020 ↔ 2025",
        body=f"""
        <section class="hero">
          <div>
            <div class="eyebrow">GeoEco Monitor</div>
            <h1>Сравнение предварительной дистанционной оценки 2020 ↔ 2025</h1>
            <p>{e(zone["name"])}</p>
          </div>
          <div class="stamp">Comparison report<br>{e(generated_at())}</div>
        </section>
        {section("Зона", definition_table([
            ("Название", zone["name"]),
            ("Slug", zone["slug"]),
            ("Тип зоны", zone["zoneType"]),
            ("Источник границы", zone["boundarySource"]),
            ("BBox", zone["bboxText"]),
        ]))}
        {section("Parent comparison", definition_table([
            ("Comparison ID", parent["comparisonId"]),
            ("Child analysis IDs", json.dumps(parent["childAnalysisIds"], ensure_ascii=False)),
            ("Status", parent["status"]),
        ]))}
        {section("Сцены и качество данных", simple_table(scene_headers, scene_rows))}
        {section("Главная таблица изменений", simple_table(
            ["Metric", "2020", "2025", "Delta", "%", "Trend"],
            comparison_rows,
        ))}
        {section("Краткая интерпретация", paragraph(payload["interpretation"]))}
        {comparison_preview_section(previews_by_year)}
        {reference_block}
        {section("Ограничения сравнения", bullet_list(comparison_limits))}
        {disclaimer()}
        """,
    )


def page(*, title: str, body: str) -> str:
    return f"""<!doctype html>
<html lang="ru">
<head>
  <meta charset="utf-8">
  <title>{e(title)}</title>
  <style>
    @page {{ size: A4; margin: 14mm; }}
    * {{ box-sizing: border-box; }}
    body {{
      margin: 0;
      color: #17211d;
      background: #f4f1e8;
      font-family: "Segoe UI", Arial, sans-serif;
      font-size: 12px;
      line-height: 1.45;
    }}
    .hero {{
      display: flex;
      justify-content: space-between;
      gap: 18px;
      padding: 22px 24px;
      border-radius: 12px;
      background: #0d3b34;
      color: #fffdf6;
      margin-bottom: 18px;
    }}
    .eyebrow {{
      color: #d79b39;
      font-weight: 800;
      text-transform: uppercase;
      letter-spacing: 0.08em;
    }}
    h1 {{ margin: 6px 0 0; font-size: 26px; line-height: 1.1; letter-spacing: 0; }}
    h2 {{ margin: 0 0 10px; font-size: 17px; color: #0d3b34; }}
    p {{ margin: 0 0 8px; }}
    section {{ break-inside: avoid; margin-bottom: 14px; }}
    .block {{
      padding: 14px;
      border: 1px solid rgba(23, 33, 29, 0.14);
      border-radius: 10px;
      background: #fffdf6;
    }}
    .stamp {{
      min-width: 180px;
      align-self: flex-start;
      border: 1px solid rgba(255,255,255,0.25);
      border-radius: 10px;
      padding: 10px 12px;
      text-align: right;
      color: #e8e2d4;
    }}
    table {{ width: 100%; border-collapse: collapse; }}
    th, td {{
      border-bottom: 1px solid rgba(23, 33, 29, 0.12);
      padding: 7px 8px;
      text-align: left;
      vertical-align: top;
    }}
    th {{ color: #647067; font-size: 11px; text-transform: uppercase; }}
    tr:last-child td {{ border-bottom: 0; }}
    .def th {{ width: 28%; text-transform: none; }}
    .grid {{ display: grid; grid-template-columns: repeat(3, 1fr); gap: 8px; }}
    .metric {{
      border: 1px solid rgba(23, 33, 29, 0.12);
      border-radius: 8px;
      padding: 10px;
      background: #f7f3e8;
    }}
    .metric span {{ display: block; color: #647067; font-size: 11px; }}
    .metric strong {{ display: block; margin-top: 4px; font-size: 17px; color: #0d3b34; }}
    .previews {{ display: grid; grid-template-columns: repeat(2, 1fr); gap: 10px; }}
    .preview {{
      border: 1px solid rgba(23, 33, 29, 0.12);
      border-radius: 8px;
      overflow: hidden;
      background: #f7f3e8;
      break-inside: avoid;
    }}
    .preview h3 {{ margin: 0; padding: 8px 10px; font-size: 12px; color: #0d3b34; }}
    .preview img {{ display: block; width: 100%; height: auto; }}
    .missing {{ padding: 28px 10px; color: #647067; text-align: center; }}
    ul {{ margin: 0; padding-left: 18px; }}
    .disclaimer {{
      border-left: 5px solid #d79b39;
      padding: 12px 14px;
      border-radius: 8px;
      background: rgba(215, 155, 57, 0.16);
      color: #483a1e;
      font-weight: 700;
    }}
  </style>
</head>
<body>{body}</body>
</html>"""


def section(title: str, content: str) -> str:
    return f'<section class="block"><h2>{e(title)}</h2>{content}</section>'


def definition_table(rows: list[tuple[str, Any]]) -> str:
    body = "".join(f"<tr><th>{e(label)}</th><td>{e(value)}</td></tr>" for label, value in rows)
    return f'<table class="def"><tbody>{body}</tbody></table>'


def simple_table(headers: list[str], rows: list[list[Any]]) -> str:
    head = "".join(f"<th>{e(header)}</th>" for header in headers)
    body = "".join(
        "<tr>" + "".join(f"<td>{e(value)}</td>" for value in row) + "</tr>" for row in rows
    )
    return f"<table><thead><tr>{head}</tr></thead><tbody>{body}</tbody></table>"


def metric_grid(rows: list[tuple[str, Any]]) -> str:
    items = "".join(
        f'<div class="metric"><span>{e(label)}</span><strong>{e(value)}</strong></div>'
        for label, value in rows
    )
    return f'<div class="grid">{items}</div>'


def preview_section(title: str, previews: list[tuple[str, str | None]]) -> str:
    cards = "".join(preview_card(label, uri) for label, uri in previews)
    return section(title, f'<div class="previews">{cards}</div>')


def comparison_preview_section(previews_by_year: dict[str, dict[str, str | None]]) -> str:
    items: list[tuple[str, str | None]] = []
    for layer in ["rgb", "ndvi", "ndbi", "ndwi"]:
        for year in ["2020", "2025"]:
            preview = previews_by_year.get(year, {}).get(layer)
            if preview is not None or layer != "ndwi":
                items.append((f"{layer.upper()} {year}", preview))
    return preview_section("Raster previews", items)


def preview_card(label: str, uri: str | None) -> str:
    if not uri:
        image = '<div class="missing">Preview недоступен</div>'
    else:
        image = f'<img alt="{e(label)}" src="{uri}">'
    return f'<div class="preview"><h3>{e(label)}</h3>{image}</div>'


def paragraph(text: str | None) -> str:
    return f"<p>{e(text or 'Нет данных.')}</p>"


def bullet_list(items: list[str]) -> str:
    visible = [item for item in items if item]
    return "<ul>" + "".join(f"<li>{e(item)}</li>" for item in visible) + "</ul>"


def disclaimer() -> str:
    return f'<section class="disclaimer">{e(DISCLAIMER)}</section>'


def _get_finished_analysis(db: Session, analysis_id: str) -> AnalysisJob:
    job = db.get(AnalysisJob, analysis_id)
    if job is None:
        raise ReportError(404, "Расчет не найден.")
    if job.status != "succeeded":
        raise ReportError(409, "PDF можно сформировать только после успешного завершения расчета.")
    return job


def _is_existing_report_current(path: Path, updated_at: datetime) -> bool:
    return path.exists() and path.stat().st_mtime >= updated_at.timestamp()


def _preview_size(
    width: int, height: int, max_width: int = 880, max_height: int = 520
) -> tuple[int, int]:
    scale = min(max_width / width, max_height / height, 1.0)
    return max(1, int(width * scale)), max(1, int(height * scale))


def _data_uri(path: Path) -> str:
    encoded = base64.b64encode(path.read_bytes()).decode("ascii")
    return f"data:image/png;base64,{encoded}"


def _write_text(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")


def generated_at() -> str:
    return datetime.now().strftime("%d.%m.%Y %H:%M")


def zone_info(slug: str, name: str, geometry: dict[str, Any], *, is_custom: int) -> dict[str, str]:
    default_zone = _default_zone(slug)
    bbox = _geometry_bbox(geometry)
    return {
        "slug": slug,
        "name": name,
        "zoneType": (
            default_zone.get("properties", {}).get("zoneType")
            if default_zone
            else "пользовательская зона"
        ),
        "geometryType": (
            "пользовательская геометрия" if is_custom else "стандартная методическая bbox-зона"
        ),
        "boundarySource": (
            default_zone.get("properties", {}).get("boundarySource")
            if default_zone and not is_custom
            else "Пользовательская зона"
        ),
        "bboxText": " ".join(f"{value:.6f}" for value in bbox),
    }


def _default_zone(slug: str) -> dict[str, Any] | None:
    zones = load_default_zones().get("features", [])
    return next((zone for zone in zones if zone.get("properties", {}).get("slug") == slug), None)


def _geometry_bbox(geometry: dict[str, Any]) -> tuple[float, float, float, float]:
    coordinates = geometry.get("coordinates", [])
    points: list[tuple[float, float]] = []

    def walk(value: Any) -> None:
        if (
            isinstance(value, list)
            and len(value) >= 2
            and isinstance(value[0], int | float)
            and isinstance(value[1], int | float)
        ):
            points.append((float(value[0]), float(value[1])))
            return
        if isinstance(value, list):
            for child in value:
                walk(child)

    walk(coordinates)
    if not points:
        return (0.0, 0.0, 0.0, 0.0)
    xs = [point[0] for point in points]
    ys = [point[1] for point in points]
    return min(xs), min(ys), max(xs), max(ys)


def scene_to_dict(scene: SceneMetadata) -> dict[str, Any]:
    return {
        "stacItemId": scene.stac_item_id,
        "collection": scene.collection,
        "datetime": scene.datetime,
        "cloudCover": scene.cloud_cover,
        "tileId": scene.tile_id,
        "referenceSceneId": scene.reference_scene_id,
        "referenceSceneFound": bool(scene.reference_scene_found),
        "referenceNote": scene.reference_note,
        "thesisReferenceId": scene.thesis_reference_id,
        "referenceDate": scene.reference_date,
        "referenceTile": scene.reference_tile,
        "referenceMatchStatus": scene.reference_match_status,
        "sceneSelectionReason": scene.scene_selection_reason,
    }


def stats_to_dict(result: AnalysisResult) -> dict[str, Any]:
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


def coverage_to_dict(coverage: CoverageMetrics) -> dict[str, Any]:
    return {
        "zoneAreaSqKm": coverage.zone_area_sq_km,
        "rasterCoverageRatio": coverage.raster_coverage_ratio,
        "validPixelRatio": coverage.valid_pixel_ratio,
        "maskedPixelRatio": coverage.masked_pixel_ratio,
        "cloudMaskedPixelRatio": coverage.cloud_masked_pixel_ratio,
        "nodataPixelRatio": coverage.nodata_pixel_ratio,
        "coverageWarning": coverage.coverage_warning,
        "methodNote": coverage.method_note,
    }


def raster_to_dict(asset: RasterAsset) -> dict[str, Any]:
    return {
        "analysisId": asset.analysis_id,
        "layer": asset.layer,
        "path": asset.path,
        "min": asset.min,
        "max": asset.max,
        "nodata": asset.nodata,
        "crs": asset.crs,
        "bounds": json.loads(asset.bounds),
    }


def e(value: Any) -> str:
    if value is None:
        return "—"
    return html.escape(str(value), quote=True)


def fmt(value: Any, digits: int = 3) -> str:
    if isinstance(value, int | float) and not isinstance(value, bool):
        if np.isnan(value):
            return "—"
        return f"{value:.{digits}f}"
    return e(value)


def pct(value: Any) -> str:
    if isinstance(value, int | float) and not isinstance(value, bool):
        return f"{value * 100:.1f}%"
    return "—"


def pct_from_percent(value: Any) -> str:
    if isinstance(value, int | float) and not isinstance(value, bool):
        return f"{value:.1f}%"
    return "—"


def cell(value: Any, metric: str) -> str:
    if metric in {"validPixelRatio", "rasterCoverageRatio"}:
        return pct(value)
    return fmt(value)


def trend_label(trend: str) -> str:
    return {
        "up": "рост",
        "down": "снижение",
        "stable": "стабильно",
        "changed": "изменился",
        "unknown": "нет данных",
    }.get(trend, trend)
