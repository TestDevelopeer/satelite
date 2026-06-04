import json
from pathlib import Path
from typing import Any

from pyproj import CRS, Transformer
from shapely.geometry import shape
from shapely.ops import transform

from app.core.config import get_settings

FIXTURES_DIR = Path(__file__).resolve().parents[1] / "fixtures"


def load_default_zones() -> dict[str, Any]:
    with (FIXTURES_DIR / "default-zones.geojson").open("r", encoding="utf-8") as file:
        return json.load(file)


def load_reference_results() -> dict[str, Any]:
    with (FIXTURES_DIR / "thesis-reference-results.json").open("r", encoding="utf-8") as file:
        return json.load(file)


def find_reference(zone_slug: str, year: int) -> dict[str, Any] | None:
    data = load_reference_results()
    return next(
        (
            result
            for result in data["results"]
            if result["zoneSlug"] == zone_slug and result["year"] == year
        ),
        None,
    )


def geometry_area_sq_km(geometry: dict[str, Any]) -> float:
    geom = shape(geometry)
    centroid = geom.centroid
    utm_zone = int((centroid.x + 180) // 6) + 1
    epsg = 32600 + utm_zone if centroid.y >= 0 else 32700 + utm_zone
    transformer = Transformer.from_crs(CRS.from_epsg(4326), CRS.from_epsg(epsg), always_xy=True)
    projected = transform(transformer.transform, geom)
    return projected.area / 1_000_000


def validate_geometry_area(geometry: dict[str, Any]) -> None:
    geom = shape(geometry)
    if geom.geom_type not in {"Polygon", "MultiPolygon"}:
        raise ValueError("Поддерживаются только GeoJSON Polygon или MultiPolygon.")
    if not geom.is_valid:
        raise ValueError("Геометрия зоны невалидна.")
    if geom.is_empty:
        raise ValueError("Геометрия зоны пустая.")

    area_km2 = geometry_area_sq_km(geometry)

    settings = get_settings()
    if area_km2 > settings.max_zone_area_km2:
        raise ValueError(
            f"Площадь зоны {area_km2:.1f} км² превышает лимит {settings.max_zone_area_km2:.1f} км²."
        )
