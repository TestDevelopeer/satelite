# Phase 3.1 — Build Stability + Comparison Demo Polish

Дата выполнения: 04.06.2026.

## Цель

Стабилизировать проект после comparison mode и улучшить демо-сценарий перед переходом к PDF/drawing/Docker.

Не добавлялись PDF, drawing tools, import/export GeoJSON, production Docker, auth и user accounts.

## Next/SWC build

Проверенная конфигурация:

- Node.js: `20.19.0`;
- npm: `10.8.2`;
- Next.js: `15.5.19`;
- package manager: `npm`;
- `.nvmrc`: `20.19.0`;
- `package.json#engines`: `>=20.19.0 <21`.

Что проверено:

- На Node `22.13.1` build уже мог завершаться с exit code `0`, но native SWC warning сохранялся.
- На Node `20.11.1` появился `EBADENGINE` от части frontend tooling, поэтому эта версия не подходит как baseline.
- На Node `20.19.0` выполнен clean reinstall:
  - удален `node_modules`;
  - выполнен `npm cache verify`;
  - выполнен `npm install`;
  - выполнен `npm run build`.
- Прямой `require('@next/swc-win32-x64-msvc')` по-прежнему падает с `ERR_DLOPEN_FAILED`.
- В системе установлен Visual C++ runtime `14.42.34433.00`, но native SWC DLL все равно не инициализируется.

Итог:

- `npm run build` завершается с exit code `0`.
- Next использует wasm fallback, в выводе остается warning:
  - `Attempted to load @next/swc-win32-x64-msvc... DLL initialization routine failed`.
- Это зафиксировано как non-blocking Windows environment warning, а не ошибка TypeScript/Next-кода проекта.

Для VPS/production рекомендуется Linux build environment, где этот Windows native DLL warning не относится к окружению.

## Tailwind

Tailwind warning `No utility classes detected` на текущей конфигурации не воспроизводится.

Оставлено:

- `tailwind.config.ts` с content paths `app`, `components`, `lib`;
- `postcss.config.mjs`;
- Tailwind directives в `app/globals.css`.

Причина: удаление Tailwind сейчас не дает пользы, но может изменить base/preflight CSS. Warning отсутствует, поэтому build pipeline оставлен без рискованной чистки.

## rasterio NotGeoreferencedWarning

Проверено на актуальных raster outputs из comparison result:

- `rgb.tif`;
- `ndvi.tif`;
- `ndwi.tif`;
- `ndbi.tif`.

У всех проверенных GeoTIFF:

- CRS: `EPSG:32637`;
- affine transform присутствует;
- bounds корректные;
- tile rendering через `render_tile_png` не воспроизводит `NotGeoreferencedWarning`.

Добавлен regression test:

- `test_tile_renderer_does_not_warn_for_georeferenced_raster`.

Итог:

- Глобальное подавление warning не добавлялось.
- Если warning появится снова, его нужно расследовать по конкретному raster path/tile request.

## Comparison demo polish

Добавлено в UI:

- overlay на карте со статусом выбранного слоя;
- понятный empty state: слой появится после завершения расчета и подготовки тайлов;
- явное указание года и слоя на карте;
- кнопка `К зоне` для fit bounds;
- bbox overlay остается поверх raster layer;
- compact summary в comparison mode:
  - изменение NDVI;
  - изменение NDBI;
  - изменение класса;
- рядом с метриками явно показан выбранный год на карте.

Ручная проверка:

- `http://localhost:3000/?comparisonId=c3608de4-b365-4761-8afb-9a2467c68208&comparisonYear=2025` открывается в dev-режиме;
- `_next/static` assets возвращают `200`, прежние `404` для `layout.css`, `main-app.js`, `app/page.js` не воспроизводятся;
- backend `GET /health` возвращает `{"status":"ok","service":"geoeco-api"}`;
- DOM содержит `.map-status.ready` с текстом `На карте: 2025 · RGB · live Sentinel-2 tiles`;
- контрольный PNG сохранен: `docs/phase-3-1-comparison-demo.png`;
- accessibility snapshot сохранен: `docs/phase-3-1-comparison-loaded-snapshot.md`.

## Ограничения

- Native `@next/swc-win32-x64-msvc` в текущем Windows окружении не загружается, но build стабильно завершается через wasm fallback.
- Comparison mode по-прежнему поддерживает только пару `[2020, 2025]`.
- Split-view карты не добавлялся.
- PDF и drawing tools отложены.

## Рекомендация для Phase 4

Следующий этап лучше делать как PDF-отчет по comparison result. Это полезнее для защиты и портфолио, чем drawing tools, потому что PDF сразу превращает live analysis/comparison в демонстрируемый артефакт.
