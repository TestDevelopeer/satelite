# Phase 3 — Comparison Mode 2020 ↔ 2025

Дата выполнения: 03.06.2026.

## Что реализовано

- Добавлена модель `ComparisonJob` для parent analysis.
- `POST /api/comparisons` создает parent comparison и два child `AnalysisJob` для 2020 и 2025 годов.
- Каждый child job остается полноценным live-анализом со своими статусом, логами, `SceneMetadata`, `CoverageMetrics`, `RasterAsset` и `AnalysisResult`.
- Parent comparison агрегирует статусы child jobs и сохраняет итоговый `result_json`.
- Поддержаны статусы `queued`, `running`, `partial`, `succeeded`, `failed`.
- Добавлены endpoints:
  - `POST /api/comparisons`;
  - `GET /api/comparisons/{comparisonId}`;
  - `GET /api/comparisons/{comparisonId}/result`.
- Comparison result включает:
  - результаты child jobs;
  - таблицу изменений;
  - delta;
  - безопасный `percentChange`;
  - тренд `up/down/stable/changed/unknown`;
  - предупреждения по ошибкам child jobs и разнице покрытия;
  - осторожную rule-based интерпретацию;
  - reference comparison из `thesis-reference-results.json` без подмены live result.
- Frontend получил режимы `Один год` и `2020 ↔ 2025`.
- В режиме сравнения UI показывает parent status, child jobs 2020/2025, выбранный год слоя на карте, карточки индексов выбранного года и нижний блок сравнения.
- Добавлен query-param deep link для проверки готового comparison result:
  - `/?comparisonId=<id>&comparisonYear=2025`.

## Как работает parent/child

1. UI отправляет `POST /api/comparisons` с зоной и годами `[2020, 2025]`.
2. Backend создает два child `AnalysisJob`.
3. Backend создает parent `ComparisonJob` и записывает `child_analysis_ids_json`.
4. Worker последовательно запускает `run_analysis_job` для 2020 и 2025.
5. Если оба child jobs успешны, parent получает `succeeded`.
6. Если один child успешен, а второй завершился ошибкой, parent получает `partial`.
7. Если оба child jobs завершились ошибкой, parent получает `failed`, но результат может содержать честные child errors.

## Ручная проверка Ростов-на-Дону

Запущен comparison:

- `comparisonId`: `c3608de4-b365-4761-8afb-9a2467c68208`;
- зона: `rostov_on_don`;
- годы: `2020`, `2025`;
- статус: `succeeded`.

Child 2020:

- `analysisId`: `43680102-6ce9-4ec6-8977-f47b613b784d`;
- STAC item: `S2B_T37TEN_20200719T081640_L2A`;
- reference match: `same_date_tile`;
- cloud cover: `0.001374`;
- raster coverage: `0.9999770176839016`;
- valid pixels: `0.9999556203551204`;
- NDVI: `0.309483140707016`;
- NDWI: `-0.2977505326271057`;
- NDBI: `-0.07506959140300751`;
- rawScore: `0.10599166378378869`;
- normalizedScore: `0.48163185050481994`;
- class: `напряженное`.

Child 2025:

- `analysisId`: `938569e7-7313-44dc-b659-dc8fc951625a`;
- STAC item: `S2A_T37TEN_20250829T082619_L2A`;
- reference match: `same_date_tile`;
- cloud cover: `0.000591`;
- raster coverage: `0.9999770176839016`;
- valid pixels: `0.9999738477092673`;
- NDVI: `0.22351530194282532`;
- NDWI: `-0.239881694316864`;
- NDBI: `0.007567204535007477`;
- rawScore: `0.04995702542364598`;
- normalizedScore: `0.2216103267918607`;
- class: `проблемное`.

Основные изменения:

- NDVI delta: `-0.08596783876419067`;
- NDWI delta: `0.0578688383102417`;
- NDBI delta: `0.08263679593801498`;
- rawScore delta: `-0.056034638360142705`;
- normalizedScore delta: `-0.2600215237129592`;
- class change: `напряженное -> проблемное`;
- warnings: нет.

Screenshot:

- `docs/phase-3-comparison-dashboard.png`;
- дополнительный высокий viewport: `docs/phase-3-comparison-dashboard-full.png`.

## Выполненные проверки

- `npm run lint` — прошло.
- `pytest` — прошло, `24 passed`.
- `ruff check` — прошло.
- `npm run build` — в Phase 3 изначально был нестабилен на Windows из-за native `@next/swc-win32-x64-msvc`; в Phase 3.1 проверен на Node `20.19.0` и завершается с exit code `0` через Next wasm fallback.

## Ограничения

- Child jobs в comparison пока выполняются последовательно в одном worker function.
- Comparison mode пока поддерживает только стандартную пару `[2020, 2025]`.
- UI не делает split-view карты; пользователь выбирает год слоя.
- Reference comparison показывается отдельно и не подменяет live result.
- PDF, drawing tools, import/export GeoJSON, production Docker и auth не реализованы.

## Что делать в Phase 4

- Добавить устойчивую очередь worker jobs для параллельного выполнения child analyses.
- Сделать более компактную visual comparison карту: split или synchronized year toggle.
- Добавить PDF-отчет только после стабилизации comparison result.
- Для production/VPS использовать Linux build environment; Windows native SWC warning задокументирован в `docs/phase-3-1-build-stability-demo-polish.md`.
