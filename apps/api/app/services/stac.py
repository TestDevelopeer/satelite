from datetime import date
from typing import Any

from pystac import Item
from pystac_client import Client
from shapely.geometry import shape

from app.core.config import get_settings
from app.services.zones import find_reference

ASSET_ALIASES = {
    "red": ("red", "B04", "B04_10m"),
    "green": ("green", "B03", "B03_10m"),
    "blue": ("blue", "B02", "B02_10m"),
    "nir": ("nir", "nir08", "B08", "B08_10m"),
    "swir": ("swir16", "B11", "B11_20m"),
    "scl": ("scl", "SCL", "SCL_20m"),
}


class SceneSelectionError(RuntimeError):
    pass


def _item_datetime(item: Item) -> str:
    value = item.properties.get("datetime")
    if value:
        return str(value)
    if item.datetime:
        return item.datetime.isoformat()
    return ""


def _cloud_cover(item: Item) -> float:
    value = item.properties.get("eo:cloud_cover", item.properties.get("cloud_cover", 100))
    try:
        return float(value)
    except (TypeError, ValueError):
        return 100.0


def _tile_id(item: Item) -> str | None:
    grid = item.properties.get("grid:code")
    if isinstance(grid, str) and grid:
        return grid.split("-")[-1]
    mgrs = item.properties.get("mgrs:utm_zone")
    latitude = item.properties.get("mgrs:latitude_band")
    square = item.properties.get("mgrs:grid_square")
    if mgrs and latitude and square:
        return f"{mgrs}{latitude}{square}"
    return None


def resolve_assets(item: Item) -> dict[str, str]:
    resolved: dict[str, str] = {}
    for logical_name, aliases in ASSET_ALIASES.items():
        for alias in aliases:
            asset = item.assets.get(alias)
            if asset:
                resolved[logical_name] = asset.href
                break
        if logical_name not in resolved:
            available = ", ".join(sorted(item.assets.keys()))
            raise SceneSelectionError(
                f"В сцене {item.id} не найден asset {logical_name}. Доступные assets: {available}"
            )
    return resolved


def search_best_scene(
    *,
    zone_slug: str,
    geometry: dict[str, Any],
    start_date: date,
    end_date: date,
    cloud_cover_max: float,
) -> tuple[Item, list[Item], dict[str, Any]]:
    settings = get_settings()
    client = Client.open(settings.stac_url)
    geom = shape(geometry)
    reference = find_reference(zone_slug, start_date.year)
    searched_reference = reference["sceneId"] if reference else None

    search = client.search(
        collections=[settings.stac_collection],
        intersects=geometry,
        datetime=f"{start_date.isoformat()}/{end_date.isoformat()}",
        query={"eo:cloud_cover": {"lte": cloud_cover_max}},
        max_items=20,
    )
    candidates = list(search.items())
    if not candidates:
        raise SceneSelectionError(
            "STAC не вернул сцен-кандидатов для выбранной зоны, периода и лимита облачности."
        )

    candidates.sort(key=lambda item: (_cloud_cover(item), abs(_coverage_gap(item, geom))))
    selected = next((item for item in candidates if item.id == searched_reference), candidates[0])

    note = {
        "searchedReferenceScene": searched_reference,
        "referenceSceneFound": bool(searched_reference and selected.id == searched_reference),
        "candidateCount": len(candidates),
        "selectedScene": selected.id,
        "referenceNote": None,
    }
    if searched_reference and selected.id != searched_reference:
        note["referenceNote"] = (
            f"Искалась reference-сцена {searched_reference}, но среди найденных STAC-кандидатов "
            f"она отсутствует. Выбрана альтернативная сцена {selected.id}; результат не является "
            "точным воспроизведением дипломного reference-расчета."
        )

    return selected, candidates, note


def _coverage_gap(item: Item, geom: Any) -> float:
    if not item.geometry:
        return 1.0
    item_geom = shape(item.geometry)
    if geom.area == 0:
        return 1.0
    coverage = item_geom.intersection(geom).area / geom.area
    return 1.0 - coverage


def scene_metadata(
    item: Item,
    assets: dict[str, str],
    reference_note: dict[str, Any],
) -> dict[str, Any]:
    return {
        "stac_item_id": item.id,
        "collection": item.collection_id or "",
        "datetime": _item_datetime(item),
        "cloud_cover": _cloud_cover(item),
        "tile_id": _tile_id(item),
        "asset_urls_used": assets,
        "reference_scene_id": reference_note.get("searchedReferenceScene"),
        "reference_scene_found": int(reference_note.get("referenceSceneFound", False)),
        "reference_note": reference_note.get("referenceNote"),
    }
