import numpy as np

INDEX_RANGES = {
    "ndvi": (-0.2, 0.8),
    "ndwi": (-0.5, 0.6),
    "ndbi": (-0.6, 0.6),
}

INDEX_RAMPS = {
    "ndvi": np.array(
        [
            [121, 72, 45],
            [214, 174, 77],
            [184, 215, 107],
            [26, 152, 80],
            [0, 104, 55],
        ],
        dtype="float32",
    ),
    "ndwi": np.array(
        [
            [116, 76, 43],
            [219, 194, 126],
            [143, 199, 190],
            [67, 147, 195],
            [5, 48, 97],
        ],
        dtype="float32",
    ),
    "ndbi": np.array(
        [
            [37, 112, 86],
            [166, 206, 150],
            [239, 218, 139],
            [214, 127, 72],
            [140, 51, 38],
        ],
        dtype="float32",
    ),
}


def colorize_index(layer: str, values: np.ndarray, nodata: float | None = None) -> np.ndarray:
    if layer not in INDEX_RANGES:
        raise ValueError(f"Неизвестный индексный слой: {layer}")

    minimum, maximum = INDEX_RANGES[layer]
    ramp = INDEX_RAMPS[layer]
    valid = np.isfinite(values)
    if nodata is not None:
        valid &= ~np.isclose(values, nodata)
    safe_values = np.where(valid, values, minimum).astype("float32")
    normalized = np.clip((safe_values - minimum) / (maximum - minimum), 0, 1)
    positions = normalized * (len(ramp) - 1)
    lower = np.floor(positions).astype("int16")
    upper = np.clip(lower + 1, 0, len(ramp) - 1)
    weight = positions - lower

    rgb = ramp[lower] * (1 - weight[..., np.newaxis]) + ramp[upper] * weight[..., np.newaxis]
    alpha = np.where(valid, 255, 0).astype("uint8")

    rgba = np.zeros((*values.shape, 4), dtype="uint8")
    rgba[..., :3] = np.clip(rgb, 0, 255).astype("uint8")
    rgba[..., 3] = alpha
    return rgba


def rgba_from_rgb_bands(bands: np.ndarray) -> np.ndarray:
    if bands.shape[0] == 4:
        return np.moveaxis(bands.astype("uint8"), 0, -1)
    rgba = np.zeros((bands.shape[1], bands.shape[2], 4), dtype="uint8")
    rgba[..., :3] = np.moveaxis(bands[:3].astype("uint8"), 0, -1)
    rgba[..., 3] = 255
    return rgba


def transparent_tile(size: int = 256) -> np.ndarray:
    return np.zeros((size, size, 4), dtype="uint8")
