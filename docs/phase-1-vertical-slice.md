# Phase 1: Vertical Slice

Дата выполнения: 2026-06-03

## Цель этапа

Получить минимально рабочую и проверяемую цепочку GeoEco Monitor без попытки сразу реализовать весь MVP:

- scaffold monorepo;
- локальный запуск frontend и backend через `npm run dev`;
- базовые API endpoints;
- методические fixtures диплома;
- live Sentinel-2 pipeline на уровне backend-кода;
- dashboard shell с выбором зоны/года, картой bbox, статусом и результатами.

## Реализовано

- Инициализирован git-репозиторий в `D:\domains\satelite`.
- Добавлен remote `https://github.com/TestDevelopeer/satelite.git`.
- Создан root `package.json` с командами:
  - `npm run dev`
  - `npm run lint`
  - `npm run build`
  - `npm run test`
  - `npm run check`
- Создан `scripts/dev.mjs`:
  - проверяет Python 3.11;
  - создает `apps/api/.venv`;
  - устанавливает backend dependencies;
  - запускает FastAPI на `8000`;
  - запускает Next.js на `3000`;
  - показывает понятную ошибку, если Python 3.11 или rasterio/GDAL недоступны.
- Создан FastAPI backend:
  - `GET /health`;
  - `GET /api/zones/defaults`;
  - `POST /api/analyses`;
  - `GET /api/analyses/{analysisId}`;
  - `GET /api/analyses/{analysisId}/result`.
- Добавлены fixtures:
  - `apps/api/app/fixtures/default-zones.geojson`;
  - `apps/api/app/fixtures/thesis-reference-results.json`.
- Реализованы backend-сервисы:
  - STAC search через Earth Search;
  - выбор Sentinel-2 L2A сцены;
  - asset mapping для Red, Green, Blue, NIR, SWIR, SCL;
  - rasterio-чтение окон;
  - приведение каналов к единой сетке;
  - SCL mask;
  - расчет NDVI, NDWI, NDBI;
  - расчет mean, median, valid pixel ratio, rawScore, normalizedScore, class_label;
  - rule-based интерпретация на русском языке.
- Создан frontend dashboard:
  - левая панель управления;
  - центральная MapLibre карта с bbox выбранной зоны;
  - правая аналитическая панель;
  - нижний блок сводки;
  - запуск анализа и polling статуса;
  - отображение scene metadata, индексов, класса, интерпретации и ограничений метода.

## Методические решения

- Итоговый `class_label` ограничен четырьмя значениями:
  - `благоприятное`;
  - `удовлетворительное`;
  - `напряженное`;
  - `проблемное`.
- Reference fixtures внесены по значениям дипломной работы.
- `default-zones.geojson` хранит прямоугольные WGS84 bbox-зоны методики.
- Fixture-значения не используются как результат live-расчета.
- Если reference-сцена не найдена в STAC, backend сохраняет честное пояснение о выбранной альтернативной сцене.
- В интерфейсе используется формулировка “предварительная дистанционная оценка”; приложение не утверждает, что измеряет или доказывает загрязнение.

## Выполненные проверки

- `npm install` — прошло.
- `npm run lint` — прошло.
- `npm run build` — прошло.
- `pytest` — прошло: `10 passed`.
- `ruff check` — прошло.
- `git diff --check` — прошло.

## Предупреждения и ограничения среды

- `npm run build` показал предупреждение Next.js: native SWC DLL не загрузился, использован fallback.
- В текущей Windows-среде не установлен Python 3.11.
- `npm run dev` остановился с ожидаемой ошибкой: `Python 3.11 не найден`.
- Попытка поставить полный backend requirements на Python 3.14 упала на `rasterio/GDAL`.
- Unit/API tests были прогнаны в минимальном venv на Python 3.14 без rasterio; live raster pipeline end-to-end не запускался.

## Не входит в Phase 1

- Raster tiles.
- PDF report.
- Comparison mode `2020 ↔ 2025`.
- Drawing tools.
- GeoJSON import/export.
- Production Docker/VPS setup.

## Следующий этап

Phase 2 должен начаться с установки Python 3.11 x64 и проверки полного `npm run dev`, затем выполнить один live analysis end-to-end и перейти к raster tile service для MapLibre layers.
