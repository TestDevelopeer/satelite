import numpy as np


def safe_divide(numerator: np.ndarray, denominator: np.ndarray) -> np.ndarray:
    result = np.full(numerator.shape, np.nan, dtype="float32")
    np.divide(numerator, denominator, out=result, where=np.abs(denominator) > 1e-6)
    return result


def ndvi(nir: np.ndarray, red: np.ndarray) -> np.ndarray:
    return safe_divide(nir - red, nir + red)


def ndwi(green: np.ndarray, nir: np.ndarray) -> np.ndarray:
    return safe_divide(green - nir, green + nir)


def ndbi(swir: np.ndarray, nir: np.ndarray) -> np.ndarray:
    return safe_divide(swir - nir, swir + nir)


def scl_valid_mask(scl: np.ndarray) -> np.ndarray:
    invalid_classes = np.array([0, 1, 3, 8, 9, 10, 11])
    return ~np.isin(scl.astype("int16"), invalid_classes)
