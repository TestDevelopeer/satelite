# Phase 4 - PDF Report for Live Analysis and Comparison Result

Дата выполнения: 04.06.2026.

## Цель

Добавлен реальный PDF-отчет для двух сценариев:

- single-year live analysis;
- comparison mode 2020 ↔ 2025.

В Phase 4 не добавлялись drawing tools, import/export GeoJSON, production Docker, auth, user accounts, billing или SaaS-фичи.

## API

Новые endpoints:

- `POST /api/reports/analysis/{analysisId}` - формирует PDF по одному расчету;
- `GET /api/reports/analysis/{analysisId}.pdf` - возвращает готовый PDF;
- `POST /api/reports/comparison/{comparisonId}` - формирует PDF по сравнению;
- `GET /api/reports/comparison/{comparisonId}.pdf` - возвращает готовый PDF.

Если PDF уже существует и source job не менялся, backend возвращает существующий файл.

## Storage

PDF:

- `data/reports/analysis/{analysisId}.pdf`;
- `data/reports/comparison/{comparisonId}.pdf`.

HTML intermediate:

- `data/reports/html/analysis/{analysisId}.html`;
- `data/reports/html/comparison/{comparisonId}.html`.

Preview PNG:

- `data/reports/assets/analysis/{analysisId}/...`;
- `data/reports/assets/comparison/{comparisonId}/{year}/...`.

HTML сохраняется намеренно: его удобно открыть в браузере и проверить layout, стили, таблицы и embedded preview images до печати PDF.

## PDF Engine

Выбран backend HTML-to-PDF pipeline:

1. Backend собирает payload из live `AnalysisJob` / `ComparisonJob`.
2. Backend генерирует preview PNG из GeoTIFF outputs.
3. Backend строит локальный HTML с inline CSS и embedded base64 images.
4. Python Playwright печатает HTML через Chromium в PDF.

Зависимость:

```powershell
apps\api\.venv\Scripts\python.exe -m pip install -r apps\api\requirements.txt
apps\api\.venv\Scripts\python.exe -m playwright install chromium
```

Если Playwright или Chromium не установлены, API возвращает понятное русское сообщение с командой установки.

## Single PDF Content

Single report включает:

- название проекта;
- тип отчета;
- дату формирования;
- зону, slug, тип зоны, bbox и источник границы;
- год и date range;
- Sentinel-2 scene metadata;
- reference date/tile/status и причину выбора сцены;
- coverage metrics;
- mean/median NDVI, NDWI, NDBI;
- rawScore, normalizedScore, classLabel;
- RGB, NDVI, NDWI, NDBI previews;
- интерпретацию;
- формулы индексов;
- ограничения метода;
- disclaimer.

## Comparison PDF Content

Comparison report включает:

- parent comparison metadata;
- child analysis ids;
- scene summary по 2020 и 2025;
- coverage и valid pixels по каждому году;
- таблицу изменений с delta, percentChange и trend;
- осторожную интерпретацию;
- RGB 2020/2025, NDVI 2020/2025, NDBI 2020/2025 и NDWI 2020/2025 previews;
- reference comparison block, если он доступен;
- ограничения сравнения;
- disclaimer.

Reference values не подменяют live result и используются только как справочный блок.

## Frontend UX

Dashboard показывает PDF-блок только после завершения расчета:

- single mode: `Сформировать PDF`;
- comparison mode: `Сформировать PDF сравнения`.

Состояния:

- `Готовим отчет`;
- `Генерируем изображения слоев`;
- `Формируем PDF`;
- `Отчет готов`;
- ошибка без stack trace.

После успешной генерации появляется ссылка `Скачать PDF`.

## Tests

Добавлены backend tests:

- missing analysis возвращает 404;
- unfinished analysis возвращает 409;
- single analysis report создает PDF file;
- comparison report создает PDF file;
- generated PDF имеет non-zero size;
- paths PDF/HTML корректны;
- missing raster preview обрабатывается через warning.

В обычных тестах PDF renderer monkeypatch-ится на минимальный валидный PDF. Реальный Chromium проверяется вручную.

## Manual Verification

Single:

1. Запустить `npm run dev`.
2. Открыть `http://localhost:3000`.
3. Выбрать Ростов-на-Дону, один год 2020.
4. Дождаться статуса `готово`.
5. Нажать `Сформировать PDF`.
6. Открыть PDF и проверить scene metadata, index stats, RGB/NDVI/NDWI/NDBI previews и disclaimer.

Comparison:

1. Открыть готовый или новый comparison Ростов-на-Дону 2020 ↔ 2025.
2. Дождаться статуса `готово` или `частично готово`.
3. Нажать `Сформировать PDF сравнения`.
4. Открыть PDF и проверить две сцены, таблицу delta, class change, raster previews, ограничения и disclaimer.

Проверенные файлы Phase 4:

- single PDF: `data/reports/analysis/43680102-6ce9-4ec6-8977-f47b613b784d.pdf`, 1 547 613 bytes, 5 pages;
- comparison PDF: `data/reports/comparison/c3608de4-b365-4761-8afb-9a2467c68208.pdf`, 2 906 938 bytes, 6 pages;
- single visual contact sheet: `docs/phase-4-single-pdf-contact-sheet.png`;
- comparison visual contact sheet: `docs/phase-4-comparison-pdf-contact-sheet.png`;
- dashboard PDF button snapshot: `docs/phase-4-dashboard-pdf-button-snapshot.md`.

Проверка выполнялась через fresh backend на `http://localhost:8001`, потому что старый dev-процесс на `8000` оставался запущенным со старым кодом и держал порт.

## Ограничения

- Для реальной PDF-печати нужен установленный Chromium для Playwright.
- PDF строится из backend data и raster outputs, не из screenshot dashboard UI.
- Если raster output отсутствует, отчет все равно может быть сформирован, но соответствующий preview будет помечен warning.
- Comparison PDF пока ориентирован на пару 2020 ↔ 2025.

## Recommendation For Phase 5

Следующий этап лучше делать как production Docker/VPS deployment:

- web;
- api;
- worker;
- postgres/postgis;
- redis;
- reverse proxy;
- volumes для rasters, reports, cache и db.

После деплоя проект можно показывать по ссылке: live-анализ, сравнение и скачиваемый PDF уже образуют законченный демонстрационный сценарий.
