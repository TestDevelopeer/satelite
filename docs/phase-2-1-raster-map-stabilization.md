# Phase 2.1: Raster Map Stabilization + Demo Readiness

Дата выполнения: 2026-06-03

## Цель

Стабилизировать raster map flow перед крупными фичами Phase 3, не добавляя PDF, drawing tools, comparison mode, production Docker, auth или SaaS-функции.

Сценарии, которые нельзя ломать:

- live STAC analysis;
- сохранение raster outputs;
- tile endpoint;
- MapLibre layers `rgb`, `ndvi`, `ndwi`, `ndbi`.

## Coverage metrics

В `GET /api/analyses/{analysisId}/result` добавлен объект `coverage`:

- `zoneAreaSqKm`;
- `rasterCoverageRatio`;
- `validPixelRatio`;
- `maskedPixelRatio`;
- `cloudMaskedPixelRatio`;
- `nodataPixelRatio`;
- `selectedSceneIntersectsZone`;
- `coverageWarning`;
- `methodNote`.

Методика расчета:

- зона берется из GeoJSON geometry анализа;
- площадь зоны считается в локальной UTM-проекции по centroid зоны;
- total pixels — пиксели внутри методической геометрии зоны на reference grid;
- nodata — отсутствие значений каналов или SCL classes `0/1`;
- cloud mask — SCL classes `3, 8, 9, 10, 11`;
- valid pixels — пиксели внутри зоны с валидными Red, Green, Blue, NIR, SWIR и допустимым SCL class;
- masked pixels — все пиксели внутри зоны, которые не попали в valid pixels.

`coverageWarning` формируется осторожно, без категоричных экологических выводов:

- неполное покрытие зоны;
- сниженная доля валидных пикселей;
- значимая облачность/тени по SCL.

## UI

В правую аналитическую панель добавлен блок “Качество данных”:

- покрытие зоны выбранной сценой;
- площадь зоны;
- валидные пиксели;
- маскированные пиксели;
- облака/тени по SCL;
- nodata;
- облачность сцены из STAC metadata;
- предупреждение для осторожной интерпретации.

## Tile cache

Rendered PNG tiles кэшируются локально:

```text
data/cache/tiles/{analysisId}/{layer}/{z}/{x}/{y}.png
```

Флаг:

```text
TILE_CACHE_ENABLED=true
```

Поведение:

- если PNG уже есть, backend отдает cache hit с диска;
- если PNG нет, backend рендерит tile, сохраняет файл и возвращает его;
- cache учитывает `analysisId`, `layer`, `z`, `x`, `y`.

Очистка вручную:

```powershell
Remove-Item -Recurse -Force data\cache\tiles
```

## COG readiness

Outputs остаются GeoTIFF, но writer усилен:

- tiled GeoTIFF;
- internal block size `256 x 256`;
- LZW compression;
- `BIGTIFF=IF_SAFER`;
- predictor для float/index layers и RGB;
- nodata для индексных слоев;
- metadata tags `GEOECO_LAYER` и `GEOECO_OUTPUT`.

`rio-cogeo` не добавлен в зависимости по умолчанию, чтобы не усложнять Windows local dev. Следующий шаг — optional COG writer или отдельный production-only COG conversion.

## Cleanup

Исправлено:

- `favicon.svg` подключен через Next metadata;
- accessibility issue с несвязанным label у группы raster layer controls;
- FastAPI `on_event` заменен на lifespan;
- SCL NaN cast warning устранен аккуратной обработкой NaN перед `astype`.

Next SWC warning на Windows пока классифицирован как non-blocking dev warning, если `npm run build` проходит успешно.

## Tests

Добавлены/обновлены tests:

- coverage metrics ratios and warning;
- tile cache hit/miss;
- result endpoint includes `coverage`;
- tile endpoint behavior remains stable.

## Ограничения

- `cloudMaskedPixelRatio` и `nodataPixelRatio` рассчитаны по доступной SCL/data mask на reference grid; это data quality metric, а не независимая валидация снимка.
- Cache не имеет TTL и eviction policy; очистка пока ручная.
- Outputs еще не являются COG.
- После `npm run build` при работающем `npm run dev` нужно перезапускать dev-сервер, потому что обе команды используют `.next`.
