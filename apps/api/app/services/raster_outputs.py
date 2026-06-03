import json
from pathlib import Path
from typing import Any

import numpy as np
import rasterio
from rasterio.warp import transform_bounds

from app.core.config import get_settings
from app.models.analysis import RasterAsset

FLOAT_NODATA = -9999.0


def save_raster_outputs(
    *,
    analysis_id: str,
    rasters: dict[str, np.ndarray],
    profile: dict[str, Any],
) -> list[RasterAsset]:
    output_dir = get_settings().rasters_dir / analysis_id
    output_dir.mkdir(parents=True, exist_ok=True)

    assets: list[RasterAsset] = []
    for layer in ("ndvi", "ndwi", "ndbi"):
        assets.append(_save_float_layer(output_dir, analysis_id, layer, rasters[layer], profile))
    assets.append(_save_rgb_layer(output_dir, analysis_id, rasters["rgb"], profile))
    return assets


def _base_profile(profile: dict[str, Any]) -> dict[str, Any]:
    return {
        "driver": "GTiff",
        "height": profile["height"],
        "width": profile["width"],
        "crs": profile["crs"],
        "transform": profile["transform"],
        "tiled": True,
        "blockxsize": 256,
        "blockysize": 256,
        "compress": "lzw",
    }


def _save_float_layer(
    output_dir: Path,
    analysis_id: str,
    layer: str,
    raster: np.ndarray,
    profile: dict[str, Any],
) -> RasterAsset:
    path = output_dir / f"{layer}.tif"
    data = np.where(np.isfinite(raster), raster, FLOAT_NODATA).astype("float32")
    write_profile = _base_profile(profile)
    write_profile.update({"count": 1, "dtype": "float32", "nodata": FLOAT_NODATA})

    with rasterio.open(path, "w", **write_profile) as dataset:
        dataset.write(data, 1)

    valid = raster[np.isfinite(raster)]
    return _metadata_from_file(
        analysis_id=analysis_id,
        layer=layer,
        path=path,
        minimum=float(np.nanmin(valid)) if valid.size else None,
        maximum=float(np.nanmax(valid)) if valid.size else None,
        nodata=FLOAT_NODATA,
    )


def _save_rgb_layer(
    output_dir: Path,
    analysis_id: str,
    raster: np.ndarray,
    profile: dict[str, Any],
) -> RasterAsset:
    path = output_dir / "rgb.tif"
    write_profile = _base_profile(profile)
    write_profile.update({"count": 4, "dtype": "uint8", "nodata": None})

    with rasterio.open(path, "w", **write_profile) as dataset:
        dataset.write(raster.astype("uint8"))

    return _metadata_from_file(
        analysis_id=analysis_id,
        layer="rgb",
        path=path,
        minimum=0,
        maximum=255,
        nodata=None,
    )


def _metadata_from_file(
    *,
    analysis_id: str,
    layer: str,
    path: Path,
    minimum: float | None,
    maximum: float | None,
    nodata: float | None,
) -> RasterAsset:
    with rasterio.open(path) as dataset:
        bounds = transform_bounds(dataset.crs, "EPSG:4326", *dataset.bounds, densify_pts=21)
        return RasterAsset(
            analysis_id=analysis_id,
            layer=layer,
            path=str(path),
            min=minimum,
            max=maximum,
            nodata=nodata,
            crs=str(dataset.crs),
            bounds=json.dumps(list(bounds), ensure_ascii=False),
        )
