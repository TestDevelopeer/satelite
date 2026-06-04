from datetime import UTC, datetime

from pystac import Item
from shapely.geometry import box

from app.services.stac import (
    _reference_note,
    parse_thesis_scene_id,
    rank_scene_candidates,
)


def _item(
    item_id: str,
    *,
    geometry: dict,
    cloud_cover: float,
    dt: datetime,
    tile: str,
    platform: str = "sentinel-2b",
) -> Item:
    return Item(
        id=item_id,
        geometry=geometry,
        bbox=None,
        datetime=dt,
        properties={
            "eo:cloud_cover": cloud_cover,
            "grid:code": f"MGRS-{tile}",
            "platform": platform,
        },
    )


def test_parse_thesis_reference_scene_id() -> None:
    reference = parse_thesis_scene_id("S2B_37TEN_20200719_1_L2A")

    assert reference.platform == "S2B"
    assert reference.tile == "37TEN"
    assert reference.scene_date.isoformat() == "2020-07-19"


def test_same_date_tile_match_is_preferred() -> None:
    zone = box(39.58, 47.11, 39.82, 47.36)
    reference = parse_thesis_scene_id("S2B_37TEN_20200719_1_L2A")
    same_date_tile = _item(
        "S2B_T37TEN_20200719T081640_L2A",
        geometry=zone.__geo_interface__,
        cloud_cover=10,
        dt=datetime(2020, 7, 19, 8, 16, tzinfo=UTC),
        tile="37TEN",
        platform="sentinel-2b",
    )
    lower_coverage = _item(
        "S2B_T37TEN_20200831T082605_L2A",
        geometry=box(39.58, 47.11, 39.64, 47.18).__geo_interface__,
        cloud_cover=0,
        dt=datetime(2020, 8, 31, 8, 26, tzinfo=UTC),
        tile="37TEN",
        platform="sentinel-2b",
    )

    ranked = rank_scene_candidates([lower_coverage, same_date_tile], zone, reference)

    assert ranked[0].item_id == "S2B_T37TEN_20200719T081640_L2A"
    assert ranked[0].reference_match_status == "same_date_tile"


def test_ranking_prefers_high_coverage_over_low_cloud() -> None:
    zone = box(39.58, 47.11, 39.82, 47.36)
    reference = parse_thesis_scene_id("S2B_37TEN_20200719_1_L2A")
    high_coverage_cloudier = _item(
        "S2B_T37TEN_20200720T081640_L2A",
        geometry=zone.__geo_interface__,
        cloud_cover=18,
        dt=datetime(2020, 7, 20, 8, 16, tzinfo=UTC),
        tile="37TEN",
    )
    low_coverage_clear = _item(
        "S2B_T37TEN_20200831T082605_L2A",
        geometry=box(39.58, 47.11, 39.64, 47.18).__geo_interface__,
        cloud_cover=0,
        dt=datetime(2020, 8, 31, 8, 26, tzinfo=UTC),
        tile="37TEN",
    )

    ranked = rank_scene_candidates([low_coverage_clear, high_coverage_cloudier], zone, reference)

    assert ranked[0].item_id == "S2B_T37TEN_20200720T081640_L2A"
    assert ranked[0].estimated_coverage > 0.95


def test_low_coverage_reference_note_warns_when_no_better_candidate() -> None:
    zone = box(39.58, 47.11, 39.82, 47.36)
    reference = parse_thesis_scene_id("S2B_37TEN_20200719_1_L2A")
    low_coverage = _item(
        "S2B_T37TEN_20200831T082605_L2A",
        geometry=box(39.58, 47.11, 39.64, 47.18).__geo_interface__,
        cloud_cover=0,
        dt=datetime(2020, 8, 31, 8, 26, tzinfo=UTC),
        tile="37TEN",
    )

    ranked = rank_scene_candidates([low_coverage], zone, reference)
    note = _reference_note(ranked[0], reference)

    assert ranked[0].estimated_coverage < 0.8
    assert note is not None
    assert "Покрытие зоны выбранной сценой снижено" in note
