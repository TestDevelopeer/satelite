# Phase 1.1: локальная проверка live Sentinel-2 расчета

Дата выполнения: 2026-06-03

## Цель

Подтвердить, что Phase 1 не только запускает scaffold, но и реально считает live Sentinel-2 данные на локальной Windows-среде с Python 3.11 x64.

## Проверенная среда

- Node.js: `v22.13.1`.
- npm: `10.9.2`.
- Python launcher: `py -3.11 --version` -> `Python 3.11.9`.
- `apps/api/.venv`: `Python 3.11.9`.
- `rasterio`: `1.4.3`, импорт успешен.

## Backend и fixtures

- `GET /health` вернул `{"status":"ok","service":"geoeco-api"}`.
- `GET /api/zones/defaults` вернул три default bbox-зоны.
- `default-zones.geojson` загружается как UTF-8.
- `thesis-reference-results.json` загружается как UTF-8 и содержит 6 reference-записей.

## Обнаруженная и исправленная проблема

Первый live run дошел до STAC и выбора сцены, но упал на rasterio:

```text
Invalid dataset dimensions : 0 x 0
```

Причина: bbox зоны в WGS84 использовался напрямую для окон чтения COG в CRS растра.

Исправление:

- bounds зоны преобразуются из `EPSG:4326` в CRS конкретного raster asset перед `from_bounds`;
- geometry зоны преобразуется в CRS растра перед `geometry_mask`;
- Blue band тоже читается и приводится к общей сетке, чтобы подтвердить чтение всех базовых assets;
- SCL mask теперь явно проверяет finite-пиксели;
- pipeline logs теперь фиксируют найденные assets Red, Green, Blue, NIR, SWIR, SCL.

## Live analysis

Запущенный анализ:

- `zoneSlug`: `rostov_on_don`;
- `year`: `2020`;
- `dateRange`: `2020-07-01` — `2020-08-15`;
- `cloudCoverMax`: `20`;
- `analysisId`: `8f7ccb64-1af5-4d82-b25a-b116d2f933bf`.

Pipeline прошел этапы:

- проверка геометрии зоны;
- поиск сцен-кандидатов;
- найдено кандидатов: `10`;
- выбрана сцена: `S2B_T37TEN_20200719T081640_L2A`;
- проверка покрытия зоны;
- найдены assets: Red, Green, Blue, NIR, SWIR, SCL;
- загрузка каналов Red, Green, Blue, NIR, SWIR, SCL;
- приведение каналов к единой сетке;
- маскирование облаков и невалидных пикселей;
- расчет NDVI, NDWI, NDBI;
- расчет статистики;
- сохранение результата;
- формирование интерпретации;
- готово.

## Выбранная STAC-сцена

- STAC item: `S2B_T37TEN_20200719T081640_L2A`.
- Collection: `sentinel-2-c1-l2a`.
- Datetime: `2020-07-19T08:26:57.192000Z`.
- Cloud cover: `0.001374`.
- Tile: `37TEN`.

Reference-сцена диплома для Ростова-на-Дону 2020:

- `S2B_37TEN_20200719_1_L2A`.

Точная строка reference ID не найдена как STAC item ID, поэтому backend честно записал warning: выбрана альтернативная STAC-сцена той же даты/тайла, результат не является точным воспроизведением дипломного reference-расчета.

## Использованные assets

- Red: `B04.tif`.
- Green: `B03.tif`.
- Blue: `B02.tif`.
- NIR: `B08.tif`.
- SWIR: `B11.tif`.
- SCL: `SCL.tif`.

Все assets были открыты и прочитаны через `rasterio`.

## Полученные live-значения

- mean NDVI: `0.309483140707016`.
- mean NDWI: `-0.2977505326271057`.
- mean NDBI: `-0.07506959140300751`.
- median NDVI: `0.316920667886734`.
- median NDWI: `-0.3125845789909363`.
- median NDBI: `-0.06010305508971214`.
- valid pixel ratio: `0.9999556203551204`.
- rawScore: `0.10599166378378869`.
- normalizedScore: `0.48163185050481994`.
- class_label: `напряженное`.

Эти значения являются live-результатом Sentinel-2 расчета и не взяты из thesis fixtures.

## Предупреждения

- Next.js продолжает показывать warning по native SWC DLL и использует fallback.
- PowerShell `Invoke-RestMethod | ConvertTo-Json` может отображать русские строки как mojibake, но Python/UTF-8 проверка API и fixtures показывает корректный текст.
- Во время правки backend uvicorn reload сбросил активное polling-соединение; после reload новый job прошел успешно.

## Что нужно перед Phase 2

- Оставить Phase 1.1 как подтвержденный baseline live pipeline.
- Улучшить сопоставление thesis reference scene ID и STAC item ID: сейчас точное ID не совпадает, хотя выбранная сцена совпадает по дате и tile.
- Добавить более явные coverage metrics для выбранной сцены.
- После этого переходить к raster tiles, не смешивая с PDF/drawing/comparison.
