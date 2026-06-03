import numpy as np

MIN_REFERENCE_SCORE = 0.0022
MAX_REFERENCE_SCORE = 0.2177
ALLOWED_CLASSES = {"благоприятное", "удовлетворительное", "напряженное", "проблемное"}


def raw_score(mean_ndvi: float, mean_ndwi: float, mean_ndbi: float) -> float:
    return 0.45 * mean_ndvi + 0.20 * mean_ndwi - 0.35 * mean_ndbi


def normalized_score(score: float) -> float:
    value = (score - MIN_REFERENCE_SCORE) / (MAX_REFERENCE_SCORE - MIN_REFERENCE_SCORE)
    return float(np.clip(value, 0.0, 1.0))


def class_label(normalized: float) -> str:
    if normalized >= 0.75:
        return "благоприятное"
    if normalized >= 0.50:
        return "удовлетворительное"
    if normalized >= 0.25:
        return "напряженное"
    return "проблемное"


def build_interpretation(
    mean_ndvi: float,
    mean_ndwi: float,
    mean_ndbi: float,
    valid_ratio: float,
) -> str:
    signals: list[str] = []
    if mean_ndvi < 0.25:
        signals.append("пониженный NDVI указывает на ослабленный растительный сигнал")
    if mean_ndbi > 0:
        signals.append(
            "положительный NDBI показывает вклад застроенных или нарушенных поверхностей"
        )
    if mean_ndwi > 0:
        signals.append("положительный NDWI отражает выраженный водный или увлажненный компонент")
    if valid_ratio < 0.7:
        signals.append("доля валидных пикселей снижена, поэтому уверенность результата ограничена")

    if not signals:
        signals.append(
            "индексные показатели не выделяют одного доминирующего неблагоприятного фактора"
        )

    return (
        "Это предварительная дистанционная оценка по Sentinel-2. "
        + "; ".join(signals)
        + ". Результат следует использовать как зону внимания и основание "
        + "для планирования натурной проверки."
    )
