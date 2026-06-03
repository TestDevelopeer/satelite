from typing import Any

import numpy as np
import rasterio
from rasterio.enums import Resampling
from rasterio.features import geometry_mask
from rasterio.warp import reproject, transform_bounds, transform_geom
from rasterio.windows import from_bounds
from shapely.geometry import shape

from app.services.indices import ndbi, ndvi, ndwi, scl_valid_mask
from app.services.scoring import build_interpretation, class_label, normalized_score, raw_score


def _window_for_geometry(dataset: Any, geometry: dict[str, Any]) -> Any:
    bounds = shape(geometry).bounds
    raster_bounds = transform_bounds("EPSG:4326", dataset.crs, *bounds, densify_pts=21)
    return from_bounds(*raster_bounds, transform=dataset.transform).round_offsets().round_lengths()


def _geometry_in_crs(geometry: dict[str, Any], dst_crs: Any) -> dict[str, Any]:
    return transform_geom("EPSG:4326", dst_crs, geometry)


def _read_reference_band(href: str, geometry: dict[str, Any]) -> tuple[np.ndarray, Any, Any]:
    with rasterio.Env(AWS_NO_SIGN_REQUEST="YES"):
        with rasterio.open(href) as dataset:
            window = _window_for_geometry(dataset, geometry)
            if window.width <= 0 or window.height <= 0:
                raise RuntimeError("Окно чтения Red band пустое после преобразования CRS.")
            band = dataset.read(1, window=window, boundless=True, fill_value=dataset.nodata)
            transform = dataset.window_transform(window)
            profile = dataset.profile.copy()
            profile.update(
                {
                    "height": band.shape[0],
                    "width": band.shape[1],
                    "transform": transform,
                    "crs": dataset.crs,
                    "nodata": dataset.nodata,
                }
            )
    return band.astype("float32"), transform, profile


def _read_to_reference(
    href: str,
    geometry: dict[str, Any],
    reference_profile: dict[str, Any],
    resampling: Resampling,
) -> np.ndarray:
    destination = np.full(
        (reference_profile["height"], reference_profile["width"]), np.nan, dtype="float32"
    )
    with rasterio.Env(AWS_NO_SIGN_REQUEST="YES"):
        with rasterio.open(href) as dataset:
            window = _window_for_geometry(dataset, geometry)
            if window.width <= 0 or window.height <= 0:
                raise RuntimeError(f"Окно чтения asset {href} пустое после преобразования CRS.")
            source = dataset.read(1, window=window, boundless=True, fill_value=dataset.nodata)
            source_transform = dataset.window_transform(window)
            reproject(
                source=source,
                destination=destination,
                src_transform=source_transform,
                src_crs=dataset.crs,
                src_nodata=dataset.nodata,
                dst_transform=reference_profile["transform"],
                dst_crs=reference_profile["crs"],
                dst_nodata=np.nan,
                resampling=resampling,
            )
    return destination.astype("float32")


def calculate_indices_from_assets(
    assets: dict[str, str],
    geometry: dict[str, Any],
) -> dict[str, Any]:
    red, transform, profile = _read_reference_band(assets["red"], geometry)
    profile["transform"] = transform
    raster_geometry = _geometry_in_crs(geometry, profile["crs"])

    blue = _read_to_reference(assets["blue"], geometry, profile, Resampling.bilinear)
    green = _read_to_reference(assets["green"], geometry, profile, Resampling.bilinear)
    nir = _read_to_reference(assets["nir"], geometry, profile, Resampling.bilinear)
    swir = _read_to_reference(assets["swir"], geometry, profile, Resampling.bilinear)
    scl = _read_to_reference(assets["scl"], geometry, profile, Resampling.nearest)

    geom_mask = geometry_mask(
        [raster_geometry],
        out_shape=red.shape,
        transform=profile["transform"],
        invert=True,
        all_touched=False,
    )
    valid = geom_mask & np.isfinite(scl) & scl_valid_mask(scl)
    valid &= np.isfinite(red) & np.isfinite(blue) & np.isfinite(green)
    valid &= np.isfinite(nir) & np.isfinite(swir)

    ndvi_array = ndvi(nir, red)
    ndwi_array = ndwi(green, nir)
    ndbi_array = ndbi(swir, nir)

    valid &= np.isfinite(ndvi_array) & np.isfinite(ndwi_array) & np.isfinite(ndbi_array)
    total_pixels = int(np.count_nonzero(geom_mask))
    valid_pixels = int(np.count_nonzero(valid))
    if total_pixels == 0 or valid_pixels == 0:
        raise RuntimeError("После маскирования не осталось валидных пикселей для расчета.")

    mean_ndvi = float(np.nanmean(ndvi_array[valid]))
    mean_ndwi = float(np.nanmean(ndwi_array[valid]))
    mean_ndbi = float(np.nanmean(ndbi_array[valid]))
    score = raw_score(mean_ndvi, mean_ndwi, mean_ndbi)
    normalized = normalized_score(score)

    ndvi_output = _masked_float_raster(ndvi_array, valid)
    ndwi_output = _masked_float_raster(ndwi_array, valid)
    ndbi_output = _masked_float_raster(ndbi_array, valid)
    rgb_output = _rgb_preview(red, green, blue, valid)

    return {
        "stats": {
            "mean_ndvi": mean_ndvi,
            "mean_ndwi": mean_ndwi,
            "mean_ndbi": mean_ndbi,
            "median_ndvi": float(np.nanmedian(ndvi_array[valid])),
            "median_ndwi": float(np.nanmedian(ndwi_array[valid])),
            "median_ndbi": float(np.nanmedian(ndbi_array[valid])),
            "valid_pixel_ratio": valid_pixels / total_pixels,
            "raw_score": float(score),
            "normalized_score": normalized,
            "class_label": class_label(normalized),
            "interpretation": build_interpretation(
                mean_ndvi,
                mean_ndwi,
                mean_ndbi,
                valid_pixels / total_pixels,
            ),
        },
        "rasters": {
            "ndvi": ndvi_output,
            "ndwi": ndwi_output,
            "ndbi": ndbi_output,
            "rgb": rgb_output,
        },
        "profile": profile,
    }


def _masked_float_raster(values: np.ndarray, valid: np.ndarray) -> np.ndarray:
    output = values.astype("float32", copy=True)
    output[~valid] = np.nan
    return output


def _rgb_preview(
    red: np.ndarray,
    green: np.ndarray,
    blue: np.ndarray,
    valid: np.ndarray,
) -> np.ndarray:
    rgb = np.stack(
        [
            _stretch_to_uint8(red, valid),
            _stretch_to_uint8(green, valid),
            _stretch_to_uint8(blue, valid),
        ],
        axis=0,
    )
    alpha = np.where(valid, 255, 0).astype("uint8")
    return np.concatenate([rgb, alpha[np.newaxis, :, :]], axis=0)


def _stretch_to_uint8(values: np.ndarray, valid: np.ndarray) -> np.ndarray:
    output = np.zeros(values.shape, dtype="uint8")
    sample = values[valid & np.isfinite(values)]
    if sample.size == 0:
        return output
    low, high = np.nanpercentile(sample, [2, 98])
    if not np.isfinite(low) or not np.isfinite(high) or high <= low:
        low = float(np.nanmin(sample))
        high = float(np.nanmax(sample))
    if high <= low:
        return output
    stretched = (values - low) / (high - low)
    output[valid] = np.clip(stretched[valid] * 255, 0, 255).astype("uint8")
    return output
