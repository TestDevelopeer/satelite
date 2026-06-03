from app.services.scoring import ALLOWED_CLASSES, class_label, normalized_score, raw_score


def test_scoring_formula_matches_thesis_reference() -> None:
    score = raw_score(mean_ndvi=0.298, mean_ndwi=-0.378, mean_ndbi=0.161)
    assert abs(score - 0.00215) < 1e-10
    assert normalized_score(score) == 0.0


def test_class_thresholds_use_only_four_allowed_labels() -> None:
    assert class_label(0.9) == "благоприятное"
    assert class_label(0.6) == "удовлетворительное"
    assert class_label(0.3) == "напряженное"
    assert class_label(0.1) == "проблемное"
    assert {class_label(value) for value in [0.1, 0.3, 0.6, 0.9]} <= ALLOWED_CLASSES
