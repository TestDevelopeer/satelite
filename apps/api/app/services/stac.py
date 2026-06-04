from dataclasses import dataclass
from datetime import date, datetime
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
MAX_STAC_CANDIDATES = 80
TOP_CANDIDATES_LIMIT = 8


class SceneSelectionError(RuntimeError):
    pass


@dataclass(frozen=True)
class ThesisReference:
    thesis_id: str
    scene_date: date
    tile: str | None
    platform: str | None


@dataclass(frozen=True)
class CandidateRank:
    item: Item
    item_id: str
    scene_date: date | None
    tile: str | None
    platform: str | None
    cloud_cover: float
    estimated_coverage: float
    date_distance_days: int | None
    same_reference_date: bool
    same_reference_tile: bool
    same_platform: bool
    reference_match_status: str
    selection_score: float


def _item_datetime(item: Item) -> str:
    value = item.properties.get("datetime")
    if value:
        return str(value)
    if item.datetime:
        return item.datetime.isoformat()
    return ""


def _item_date(item: Item) -> date | None:
    value = _item_datetime(item)
    if not value:
        return None
    try:
        return datetime.fromisoformat(value.replace("Z", "+00:00")).date()
    except ValueError:
        try:
            return date.fromisoformat(value[:10])
        except ValueError:
            return None


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


def _platform_from_text(value: str | None) -> str | None:
    if not value:
        return None
    normalized = value.upper().replace("SENTINEL-2", "S2").replace("SENTINEL_2", "S2")
    if "S2A" in normalized or normalized.endswith("2A"):
        return "S2A"
    if "S2B" in normalized or normalized.endswith("2B"):
        return "S2B"
    return None


def _item_platform(item: Item) -> str | None:
    platform = _platform_from_text(str(item.properties.get("platform", "")))
    if platform:
        return platform
    return _platform_from_text(item.id)


def parse_thesis_scene_id(scene_id: str) -> ThesisReference:
    parts = scene_id.split("_")
    if len(parts) < 4:
        raise ValueError(f"Некорректный thesis scene id: {scene_id}")
    platform = _platform_from_text(parts[0])
    tile = parts[1] or None
    try:
        scene_date = date.fromisoformat(f"{parts[2][0:4]}-{parts[2][4:6]}-{parts[2][6:8]}")
    except (IndexError, ValueError) as exc:
        raise ValueError(f"Некорректная дата в thesis scene id: {scene_id}") from exc
    return ThesisReference(thesis_id=scene_id, scene_date=scene_date, tile=tile, platform=platform)


def thesis_reference_from_fixture(reference: dict[str, Any] | None) -> ThesisReference | None:
    if not reference:
        return None
    parsed = parse_thesis_scene_id(reference["sceneId"])
    if reference.get("sceneDate"):
        return ThesisReference(
            thesis_id=parsed.thesis_id,
            scene_date=date.fromisoformat(reference["sceneDate"]),
            tile=parsed.tile,
            platform=parsed.platform,
        )
    return parsed


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
    thesis_reference = thesis_reference_from_fixture(reference)

    search = client.search(
        collections=[settings.stac_collection],
        intersects=geometry,
        datetime=f"{start_date.isoformat()}/{end_date.isoformat()}",
        query={"eo:cloud_cover": {"lte": cloud_cover_max}},
        max_items=MAX_STAC_CANDIDATES,
    )
    candidates = list(search.items())
    if not candidates:
        raise SceneSelectionError(
            "STAC не вернул сцен-кандидатов для выбранной зоны, периода и лимита облачности."
        )

    ranked = rank_scene_candidates(candidates, geom, thesis_reference)
    selected_rank = ranked[0]
    selected = selected_rank.item

    note = {
        "searchedReferenceScene": thesis_reference.thesis_id if thesis_reference else None,
        "thesisReferenceId": thesis_reference.thesis_id if thesis_reference else None,
        "referenceDate": thesis_reference.scene_date.isoformat() if thesis_reference else None,
        "referenceTile": thesis_reference.tile if thesis_reference else None,
        "referenceSceneFound": bool(
            thesis_reference and selected_rank.reference_match_status == "exact_id"
        ),
        "referenceMatchStatus": selected_rank.reference_match_status,
        "sceneSelectionReason": _selection_reason(selected_rank, thesis_reference),
        "candidateCount": len(candidates),
        "selectedScene": selected.id,
        "topCandidates": [_rank_to_summary(rank) for rank in ranked[:TOP_CANDIDATES_LIMIT]],
        "referenceNote": None,
    }
    note["referenceNote"] = _reference_note(selected_rank, thesis_reference)

    return selected, candidates, note


def rank_scene_candidates(
    candidates: list[Item],
    geom: Any,
    thesis_reference: ThesisReference | None,
) -> list[CandidateRank]:
    ranked = [
        _rank_candidate(item=item, geom=geom, thesis_reference=thesis_reference)
        for item in candidates
    ]
    ranked.sort(key=lambda rank: rank.selection_score, reverse=True)

    selected = ranked[0]
    if thesis_reference and selected.estimated_coverage < 0.8:
        high_coverage = [rank for rank in ranked if rank.estimated_coverage >= 0.95]
        if high_coverage:
            return high_coverage + [rank for rank in ranked if rank not in high_coverage]
    return ranked


def _rank_candidate(
    *,
    item: Item,
    geom: Any,
    thesis_reference: ThesisReference | None,
) -> CandidateRank:
    scene_date = _item_date(item)
    tile = _tile_id(item)
    platform = _item_platform(item)
    cloud_cover = _cloud_cover(item)
    estimated_coverage = _estimated_coverage(item, geom)
    date_distance_days = (
        abs((scene_date - thesis_reference.scene_date).days)
        if scene_date and thesis_reference
        else None
    )
    same_reference_date = bool(
        scene_date and thesis_reference and scene_date == thesis_reference.scene_date
    )
    same_reference_tile = bool(tile and thesis_reference and tile == thesis_reference.tile)
    same_platform = bool(platform and thesis_reference and platform == thesis_reference.platform)
    reference_match_status = _reference_match_status(
        item_id=item.id,
        same_reference_date=same_reference_date,
        same_reference_tile=same_reference_tile,
        same_platform=same_platform,
        date_distance_days=date_distance_days,
        thesis_reference=thesis_reference,
    )
    selection_score = _selection_score(
        estimated_coverage=estimated_coverage,
        cloud_cover=cloud_cover,
        same_reference_date=same_reference_date,
        same_reference_tile=same_reference_tile,
        same_platform=same_platform,
        date_distance_days=date_distance_days,
        thesis_reference=thesis_reference,
    )
    return CandidateRank(
        item=item,
        item_id=item.id,
        scene_date=scene_date,
        tile=tile,
        platform=platform,
        cloud_cover=cloud_cover,
        estimated_coverage=estimated_coverage,
        date_distance_days=date_distance_days,
        same_reference_date=same_reference_date,
        same_reference_tile=same_reference_tile,
        same_platform=same_platform,
        reference_match_status=reference_match_status,
        selection_score=selection_score,
    )


def _selection_score(
    *,
    estimated_coverage: float,
    cloud_cover: float,
    same_reference_date: bool,
    same_reference_tile: bool,
    same_platform: bool,
    date_distance_days: int | None,
    thesis_reference: ThesisReference | None,
) -> float:
    score = estimated_coverage * 1000
    score += max(0.0, 100.0 - cloud_cover) * 0.4
    if thesis_reference:
        if same_reference_date and same_reference_tile:
            score += 450
        elif same_reference_tile:
            score += 150
        if same_platform:
            score += 30
        if date_distance_days is not None:
            score += max(0, 90 - date_distance_days) * 3
    return score


def _reference_match_status(
    *,
    item_id: str,
    same_reference_date: bool,
    same_reference_tile: bool,
    same_platform: bool,
    date_distance_days: int | None,
    thesis_reference: ThesisReference | None,
) -> str:
    if thesis_reference is None:
        return "not_found"
    if item_id == thesis_reference.thesis_id:
        return "exact_id"
    if same_reference_date and same_reference_tile and (
        same_platform or thesis_reference.platform is None
    ):
        return "same_date_tile"
    if same_reference_tile and date_distance_days is not None and date_distance_days <= 45:
        return "same_tile_near_date"
    return "alternative"


def _estimated_coverage(item: Item, geom: Any) -> float:
    if not item.geometry:
        return 0.0
    item_geom = shape(item.geometry)
    if geom.area == 0:
        return 0.0
    coverage = item_geom.intersection(geom).area / geom.area
    return max(0.0, min(1.0, coverage))


def _rank_to_summary(rank: CandidateRank) -> dict[str, Any]:
    return {
        "itemId": rank.item_id,
        "date": rank.scene_date.isoformat() if rank.scene_date else None,
        "tile": rank.tile,
        "platform": rank.platform,
        "cloudCover": rank.cloud_cover,
        "estimatedCoverage": rank.estimated_coverage,
        "selectionScore": round(rank.selection_score, 3),
        "referenceMatchStatus": rank.reference_match_status,
    }


def _selection_reason(rank: CandidateRank, thesis_reference: ThesisReference | None) -> str:
    if thesis_reference and rank.reference_match_status in {"exact_id", "same_date_tile"}:
        return "Выбрана сцена, совпадающая с датой и тайлом дипломной reference-сцены."
    if thesis_reference:
        return (
            "Точная reference-сцена не найдена, выбрана лучшая альтернатива по покрытию, "
            "облачности и близости к дипломной reference-сцене."
        )
    return "Выбрана лучшая сцена по покрытию зоны и облачности среди STAC-кандидатов."


def _reference_note(rank: CandidateRank, thesis_reference: ThesisReference | None) -> str | None:
    if thesis_reference is None:
        return None
    if rank.reference_match_status in {"exact_id", "same_date_tile"}:
        return "Выбрана сцена, совпадающая с датой и тайлом дипломной reference-сцены."
    warning = (
        "Точная reference-сцена не найдена, выбрана лучшая альтернатива по покрытию и облачности."
    )
    if rank.estimated_coverage < 0.8:
        warning += (
            " Покрытие зоны выбранной сценой снижено, результат требует осторожной "
            "интерпретации."
        )
    return warning


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
        "thesis_reference_id": reference_note.get("thesisReferenceId"),
        "reference_date": reference_note.get("referenceDate"),
        "reference_tile": reference_note.get("referenceTile"),
        "reference_match_status": reference_note.get("referenceMatchStatus"),
        "scene_selection_reason": reference_note.get("sceneSelectionReason"),
        "candidate_count": reference_note.get("candidateCount"),
        "top_candidates": reference_note.get("topCandidates", []),
    }
