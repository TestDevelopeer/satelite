# GeoEco Monitor v0.1.0 MVP Release Candidate

## Статус

Release-candidate подготовлен для финального QA, защиты диплома и portfolio-показа.

Публичный URL: ожидает VPS/domain credentials.

## Что входит в MVP

- Публичный аналитический дашборд дистанционного экологического мониторинга.
- Live Sentinel-2 L2A analysis через Earth Search STAC.
- Методические bbox-зоны диплома в WGS84.
- Расчет NDVI, NDWI, NDBI.
- Классы предварительной оценки:
  - благоприятное;
  - удовлетворительное;
  - напряженное;
  - проблемное.
- Coverage metrics:
  - покрытие зоны сценой;
  - валидные пиксели;
  - облака/тени по SCL;
  - nodata.
- Карта анализа с RGB/NDVI/NDWI/NDBI raster layers.
- Comparison mode 2020 ↔ 2025.
- PDF reports для single analysis и comparison.
- Методическая страница `/methodology`.
- Portfolio page `/about`.
- Production Docker stack:
  - Caddy reverse proxy;
  - Next.js web;
  - FastAPI API;
  - PostgreSQL/PostGIS;
  - Redis;
  - RQ worker;
  - persistent volumes.

## Рекомендуемый demo scenario

1. Открыть главную страницу.
2. Показать `/methodology`.
3. Вернуться на dashboard.
4. Нажать “Подготовить демо-сценарий”.
5. Показать, что выбран Ростов-на-Дону и режим 2020 ↔ 2025.
6. Нажать “Запустить сравнение”.
7. Показать два дочерних расчета.
8. Переключить RGB/NDVI/NDBI.
9. Показать блок качества данных.
10. Показать таблицу изменений.
11. Сформировать и скачать PDF.
12. Проговорить disclaimer.

Подробный сценарий: `docs/DEMO_WALKTHROUGH.md`.

## Production requirements

- VPS Linux x64.
- Docker Engine.
- Docker Compose plugin.
- 4 GB RAM minimum, лучше 6-8 GB для live raster processing и PDF.
- 2 vCPU minimum, лучше 4 vCPU.
- Диск от 30 GB с запасом под rasters/reports/cache.
- Домен и DNS A record на VPS для HTTPS через Caddy.

## Проверено локально

- `npm run lint`
- `npm run build`
- `npm --workspace apps/web run test`
- `apps\api\.venv\Scripts\python.exe -m pytest`
- `apps\api\.venv\Scripts\python.exe -m ruff check`
- `docker compose -f docker-compose.prod.yml config`
- `git diff --check`

Production Docker smoke проверен локально 04.06.2026:

- `/health` через Caddy на `http://localhost:18083/health`: `{"status":"ok","service":"geoeco-api"}`;
- frontend через Caddy на `http://localhost:18083/`: HTTP 200;
- `/methodology`: HTTP 200;
- `/about`: HTTP 200;
- worker logs listening;
- RQ smoke job processed: `38d4e030-7849-4b49-9008-05dbefd6adc3`;
- `rasterio` import внутри API container: `1.4.3`;
- Playwright Chromium start внутри API container: `chromium_ok`.

## Production hardening

- `.env.production` находится в `.gitignore`.
- `.env.production.example` содержит все production env variables без реальных секретов.
- Production API использует `JOB_EXECUTION_MODE=rq`.
- Queue overload возвращает понятную ошибку.
- PDF downloads валидируют id и не допускают path traversal.
- Tile endpoint не принимает произвольный path, а использует только `RasterAsset` из DB.
- Публичных debug/smoke endpoints нет.
- CORS настраивается через `CORS_ALLOWED_ORIGINS`; для Caddy same-origin production можно оставить пустым.

## Known non-blocking warnings

- Windows Next.js SWC warning:
  `Attempted to load @next/swc-win32-x64-msvc`.
  Build завершается с exit code `0`.
- `git diff --check` на Windows выводит CRLF normalization warnings.
- `npm install --package-lock-only` ранее показывал `2 moderate` npm audit warnings.
- `npm audit --audit-level=moderate` показывает 2 moderate warnings в цепочке `next -> postcss`.
  Автоматический `npm audit fix --force` предлагает переход на неподходящую major/minor-ветку Next.js, поэтому не применялся.

## Ограничения

- Приложение не доказывает загрязнение и не формирует официальное экологическое заключение.
- Результат является предварительной дистанционной оценкой и требует лабораторной/натурной проверки.
- Пользовательские drawing tools пока не реализованы.
- Production DB migrations пока не вынесены в отдельный migration tool.
- Comparison child jobs внутри worker выполняются последовательно.
- Публичный URL еще не получен, потому что VPS/domain credentials не предоставлены в текущем окружении.

## Следующий шаг

Получить VPS/IP/domain/SSH credentials, выполнить `DEPLOY_VPS.md`, провести public smoke test и обновить этот документ публичной ссылкой.
