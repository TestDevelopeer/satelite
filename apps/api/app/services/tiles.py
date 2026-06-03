from io import BytesIO
from pathlib import Path

import numpy as np
import rasterio
from PIL import Image
from rasterio.enums import Resampling
from rasterio.transform import from_bounds
from rasterio.warp import reproject, transform_bounds

from app.services.colorize import colorize_index, rgba_from_rgb_bands, transparent_tile

WEB_MERCATOR_HALF_WORLD = 20037508.342789244
TILE_SIZE = 256


def render_tile_png(path: str, layer: str, z: int, x: int, y: int, nodata: float | None) -> bytes:
    raster_path = Path(path)
    if not raster_path.exists():
        raise FileNotFoundError(f"Raster layer file not found: {path}")

    bounds = _tile_bounds_mercator(z, x, y)
    with rasterio.open(raster_path) as dataset:
        if not _intersects_dataset(dataset, bounds):
            return encode_png(transparent_tile(TILE_SIZE))

        source_nodata = nodata if nodata is not None else dataset.nodata
        tile_transform = from_bounds(*bounds, TILE_SIZE, TILE_SIZE)
        if layer == "rgb":
            data = np.zeros((4, TILE_SIZE, TILE_SIZE), dtype="uint8")
            for band_index in range(1, 5):
                reproject(
                    source=rasterio.band(dataset, band_index),
                    destination=data[band_index - 1],
                    src_transform=dataset.transform,
                    src_crs=dataset.crs,
                    dst_transform=tile_transform,
                    dst_crs="EPSG:3857",
                    src_nodata=source_nodata,
                    dst_nodata=0,
                    resampling=Resampling.bilinear,
                )
            rgba = rgba_from_rgb_bands(data)
        else:
            fill_value = source_nodata if source_nodata is not None else np.nan
            data = np.full((TILE_SIZE, TILE_SIZE), fill_value, dtype="float32")
            reproject(
                source=rasterio.band(dataset, 1),
                destination=data,
                src_transform=dataset.transform,
                src_crs=dataset.crs,
                dst_transform=tile_transform,
                dst_crs="EPSG:3857",
                src_nodata=source_nodata,
                dst_nodata=source_nodata,
                resampling=Resampling.bilinear,
            )
            rgba = colorize_index(layer, data.astype("float32"), source_nodata)
    return encode_png(rgba)


def encode_png(rgba: np.ndarray) -> bytes:
    image = Image.fromarray(rgba, mode="RGBA")
    output = BytesIO()
    image.save(output, format="PNG")
    return output.getvalue()


def _tile_bounds_mercator(z: int, x: int, y: int) -> tuple[float, float, float, float]:
    tiles = 2**z
    tile_span = (WEB_MERCATOR_HALF_WORLD * 2) / tiles
    minx = -WEB_MERCATOR_HALF_WORLD + x * tile_span
    maxx = minx + tile_span
    maxy = WEB_MERCATOR_HALF_WORLD - y * tile_span
    miny = maxy - tile_span
    return minx, miny, maxx, maxy


def _intersects_dataset(dataset: rasterio.DatasetReader, bounds_3857: tuple[float, ...]) -> bool:
    raster_bounds = transform_bounds(dataset.crs, "EPSG:3857", *dataset.bounds, densify_pts=21)
    minx, miny, maxx, maxy = bounds_3857
    rminx, rminy, rmaxx, rmaxy = raster_bounds
    return not (maxx <= rminx or minx >= rmaxx or maxy <= rminy or miny >= rmaxy)
