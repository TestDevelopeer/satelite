from app.services.zones import load_default_zones, load_reference_results


def test_default_zones_are_rectangular_bbox_polygons() -> None:
    zones = load_default_zones()
    assert len(zones["features"]) == 3
    for feature in zones["features"]:
        bbox = feature["bbox"]
        coords = feature["geometry"]["coordinates"][0]
        assert coords == [
            [bbox[0], bbox[1]],
            [bbox[2], bbox[1]],
            [bbox[2], bbox[3]],
            [bbox[0], bbox[3]],
            [bbox[0], bbox[1]],
        ]


def test_reference_results_use_allowed_classes() -> None:
    data = load_reference_results()
    classes = {result["class"] for result in data["results"]}
    assert classes <= {"благоприятное", "удовлетворительное", "напряженное", "проблемное"}
    shakhty_2025 = next(
        result
        for result in data["results"]
        if result["zoneSlug"] == "shakhty" and result["year"] == 2025
    )
    assert shakhty_2025["sceneId"] == "S2A_37UFP_20250819_1_L2A"
    assert shakhty_2025["class"] == "проблемное"
