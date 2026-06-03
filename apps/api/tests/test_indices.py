import numpy as np

from app.services.indices import ndbi, ndvi, ndwi, safe_divide, scl_valid_mask


def test_safe_divide_returns_nan_on_zero_denominator() -> None:
    result = safe_divide(np.array([1.0, 1.0]), np.array([2.0, 0.0]))
    assert result[0] == 0.5
    assert np.isnan(result[1])


def test_ndvi_formula() -> None:
    result = ndvi(np.array([0.6]), np.array([0.2]))
    assert np.isclose(result[0], 0.5)


def test_ndwi_formula() -> None:
    result = ndwi(np.array([0.2]), np.array([0.6]))
    assert np.isclose(result[0], -0.5)


def test_ndbi_formula() -> None:
    result = ndbi(np.array([0.4]), np.array([0.2]))
    assert np.isclose(result[0], 1 / 3)


def test_scl_valid_mask_excludes_cloud_and_invalid_classes() -> None:
    scl = np.array([0, 1, 3, 4, 5, 6, 8, 9, 10, 11])
    mask = scl_valid_mask(scl)
    assert mask.tolist() == [False, False, False, True, True, True, False, False, False, False]
