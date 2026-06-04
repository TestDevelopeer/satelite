# Phase 2: Raster Tile Service + MapLibre Raster Layers

Дата выполнения: 2026-06-03

## Цель

После успешного live Sentinel-2 расчета показать на карте реальные растровые слои, построенные из рассчитанных live outputs:

- RGB;
- NDVI;
- NDWI;
- NDBI.

PDF, drawing tools, comparison mode, production Docker и auth в этот этап не входили.

## Backend

После live calculation backend сохраняет raster outputs в:

```text
data/rasters/{analysisId}/rgb.tif
data/rasters/{analysisId}/ndvi.tif
data/rasters/{analysisId}/ndwi.tif
data/rasters/{analysisId}/ndbi.tif
```

Для `analysisId = d81dec1d-bc03-40d4-af5d-91e17366856b` были сохранены:

- `rgb.tif` — 4-band RGBA, `1842 x 2795`, `EPSG:32637`;
- `ndvi.tif` — 1-band float32, `1842 x 2795`, `EPSG:32637`;
- `ndwi.tif` — 1-band float32, `1842 x 2795`, `EPSG:32637`;
- `ndbi.tif` — 1-band float32, `1842 x 2795`, `EPSG:32637`.

Добавлена модель `RasterAsset`:

- `analysis_id`;
- `layer`;
- `path`;
- `min`;
- `max`;
- `nodata`;
- `crs`;
- `bounds`.

`GET /api/analyses/{analysisId}/result` теперь возвращает `rasterLayers` с tile URL template.

## Tile endpoint

Реализован endpoint:

```text
GET /api/tiles/{analysisId}/{layer}/{z}/{x}/{y}.png
```

Поддерживаемые `layer`:

- `rgb`;
- `ndvi`;
- `ndwi`;
- `ndbi`.

Поведение:

- missing `analysisId` -> `404`;
- invalid/missing layer -> `404`;
- job not succeeded -> `409`;
- tile вне bounds -> transparent PNG;
- ошибки чтения файла возвращаются понятным API error, без stack trace в UI.

Tile rendering использует `rasterio.warp.reproject` в WebMercator tile grid `256 x 256`, поэтому частично внешние MapLibre tiles не требуют `boundless` WarpedVRT reads.

## Цветовые шкалы

Backend цветизует индексные тайлы стабильно между анализами:

- NDVI: `-0.2` to `0.8`;
- NDWI: `-0.5` to `0.6`;
- NDBI: `-0.6` to `0.6`.

NaN/nodata пиксели становятся прозрачными.

## Frontend

Dashboard теперь:

- получает `rasterLayers` из result endpoint;
- добавляет MapLibre raster source/layer по `tileUrl`;
- сохраняет bbox polygon overlay поверх raster layer;
- поддерживает переключение RGB / NDVI / NDWI / NDBI;
- поддерживает opacity slider;
- показывает русские легенды для выбранного слоя;
- корректно остается пустым до появления result.

## Live verification

Запущенный live analysis:

- `analysisId`: `d81dec1d-bc03-40d4-af5d-91e17366856b`;
- `zoneSlug`: `rostov_on_don`;
- `year`: `2020`;
- `dateRange`: `2020-07-01` — `2020-08-15`;
- selected STAC item: `S2B_T37TEN_20200719T081640_L2A`.

Live stats:

- mean NDVI: `0.309483140707016`;
- mean NDWI: `-0.2977505326271057`;
- mean NDBI: `-0.07506959140300751`;
- class_label: `напряженное`.

Проверены непустые PNG tiles по центру зоны:

- `rgb`: HTTP `200`, `image/png`;
- `ndvi`: HTTP `200`, `image/png`;
- `ndwi`: HTTP `200`, `image/png`;
- `ndbi`: HTTP `200`, `image/png`.

Дополнительная UI-проверка через браузер:

- dashboard открыт на `http://localhost:3000/`;
- из UI запущен analysis `400f0544-d617-494d-b964-c9b92f90d78f`;
- выбранная UI-сцена: `S2B_T37TEN_20200831T082605_L2A`;
- отображено честное предупреждение, что reference-сцена `S2B_37TEN_20200719_1_L2A` не найдена среди STAC-кандидатов и выбрана альтернативная сцена;
- переключатели `RGB`, `NDVI`, `NDWI`, `NDBI` обновляют легенду слоя;
- opacity slider обновляет значение в интерфейсе;
- MapLibre запрашивает реальные тайлы `/api/tiles/{analysisId}/rgb/...png`, `/ndvi/...png`, `/ndwi/...png`, `/ndbi/...png`, все проверенные запросы вернули HTTP `200`;
- screenshots сохранены в `data/cache/phase-2-dashboard-ndvi-result.png` и `data/cache/phase-2-dashboard-ndbi-opacity.png`.

DevTools console во время проверки показал только dev-шум:

- `favicon.ico` HTTP `404`;
- browser issue `No label associated with a form field`;
- React DevTools informational message.

Эти сообщения не блокируют raster layer flow, но favicon и form-label warning стоит почистить перед публичной демонстрацией.

## Исправления по ходу этапа

- Сохранение job переведено с FastAPI `BackgroundTasks` на прямой `ThreadPoolExecutor.submit`, чтобы API оставался отзывчивее во время расчета.
- GeoTIFF output пишет LZW-compressed tiled files.
- Tile renderer переписан с `WarpedVRT + boundless` на прямой `reproject` в tile grid.

## Ограничения

- Outputs пока GeoTIFF, не COG; структура подготовлена так, чтобы позже заменить writer на COG.
- RGB layer — визуальный RGBA preview с percentile stretch, не полноценная radiometric RGB product.
- Score/integral raster layer пока не реализован.
- Coverage metrics для выбранной сцены еще не добавлены в Phase 2; это закрывается в Phase 2.1.

## Phase 2.1 note

Промежуточный этап `Phase 2.1 — Raster Map Stabilization + Demo Readiness` добавляет coverage metrics, tile cache, favicon/accessibility cleanup и FastAPI lifespan. См. `docs/phase-2-1-raster-map-stabilization.md`.

## Следующий этап

Phase 3 логично посвятить улучшению UX и устойчивости raster map:

- coverage metrics;
- более быстрые COG outputs;
- кэширование rendered tiles;
- затем custom drawing tools или comparison mode, но не смешивать оба направления одновременно.
