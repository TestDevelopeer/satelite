from app.services.raster_reader import build_coverage_metrics


def test_build_coverage_metrics_ratios_and_warning() -> None:
    geometry = {
        "type": "Polygon",
        "coordinates": [
            [
                [39.5, 47.2],
                [39.6, 47.2],
                [39.6, 47.3],
                [39.5, 47.3],
                [39.5, 47.2],
            ]
        ],
    }

    coverage = build_coverage_metrics(
        geometry=geometry,
        total_pixels=100,
        valid_pixels=40,
        nodata_pixels=20,
        cloud_pixels=25,
    )

    assert coverage["zone_area_sq_km"] > 0
    assert coverage["raster_coverage_ratio"] == 0.8
    assert coverage["valid_pixel_ratio"] == 0.4
    assert coverage["masked_pixel_ratio"] == 0.6
    assert coverage["cloud_masked_pixel_ratio"] == 0.25
    assert coverage["nodata_pixel_ratio"] == 0.2
    assert coverage["selected_scene_intersects_zone"] is True
    assert "покрытие зоны" in coverage["coverage_warning"]
    assert "SCL classes 3, 8, 9, 10, 11" in coverage["method_note"]
