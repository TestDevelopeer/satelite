# Phase 5 — Production Docker + VPS Deployment

## Цель

Подготовить production-контур для VPS без изменения локального сценария разработки. Локально проект по-прежнему запускается через `npm run dev`; Docker используется только для production/VPS и smoke-проверок.

## Что реализовано

- Добавлены production Dockerfiles для FastAPI backend и Next.js frontend.
- Добавлен `docker-compose.prod.yml` с сервисами `proxy`, `web`, `api`, `postgres/postgis`, `redis` и worker-сервисом.
- Добавлен Caddy reverse proxy:
  - `/health` проксируется в backend;
  - `/api/*` проксируется в backend;
  - остальные запросы идут в Next.js frontend.
- Добавлены persistent volumes для rasters, reports, cache, logs, db и Caddy.
- Backend settings научены читать production-пути хранения через env:
  - `STORAGE_ROOT`;
  - `RASTER_STORAGE_DIR`;
  - `REPORT_STORAGE_DIR`;
  - `CACHE_STORAGE_DIR`.
- Добавлен `psycopg[binary]` для PostgreSQL/PostGIS production URL.
- Playwright PDF renderer запускает Chromium с `--no-sandbox` для контейнерного root-процесса.
- Добавлены `.env.production.example` и `DEPLOY_VPS.md`.

## Ключевые файлы

- `.dockerignore`
- `.env.production.example`
- `DEPLOY_VPS.md`
- `docker-compose.prod.yml`
- `docker/Caddyfile`
- `apps/api/Dockerfile`
- `apps/web/Dockerfile`
- `apps/api/app/core/config.py`
- `apps/api/app/services/reports.py`
- `apps/api/requirements.txt`
- `apps/web/package.json`
- `README.md`

## Ограничения

- После Phase 6 worker выполняет production-задачи через Redis/RQ. В Phase 5 он был подготовлен как production-сервисный слой.
- Phase 5 не добавляет auth, drawing tools, import/export GeoJSON, production миграции, PDF-изменения или comparison-логику.
- Результат приложения остается предварительной дистанционной оценкой и не заменяет лабораторные измерения, экспертизу и натурное обследование.

## Выполненные команды

```powershell
npm install --package-lock-only
docker compose --profile worker -f docker-compose.prod.yml config
docker compose -f docker-compose.prod.yml build
$env:HTTP_PORT="18081"; $env:HTTPS_PORT="18443"; $env:PUBLIC_DOMAIN=":80"; docker compose -p geoeco_phase5 -f docker-compose.prod.yml up -d
curl http://localhost:18081/health
curl -o NUL -w "frontend_http=%{http_code}\n" http://localhost:18081/
docker compose -p geoeco_phase5 -f docker-compose.prod.yml exec -T api python -c "import rasterio; print(rasterio.__version__)"
docker compose -p geoeco_phase5 -f docker-compose.prod.yml exec -T api python -c "from playwright.sync_api import sync_playwright; p=sync_playwright().start(); b=p.chromium.launch(args=['--no-sandbox']); print('chromium ok'); b.close(); p.stop()"
docker compose -p geoeco_phase5 -f docker-compose.prod.yml down
npm run lint
npm run build
apps\api\.venv\Scripts\python.exe -m pytest
apps\api\.venv\Scripts\python.exe -m ruff check
git diff --check
```

## Результаты проверок

- `docker compose --profile worker -f docker-compose.prod.yml config`: прошел.
- `docker compose -f docker-compose.prod.yml build`: прошел, образы `satelite-api` и `satelite-web` собраны.
- Production smoke через Caddy на `http://localhost:18081`: `/health` вернул `{"status":"ok","service":"geoeco-api"}`.
- Frontend через Caddy: HTTP `200`.
- `rasterio` внутри API-контейнера: `1.4.3`.
- Playwright Chromium внутри API-контейнера: `chromium ok`.
- `npm run lint`: прошел.
- `npm run build`: прошел; Windows SWC warning остался non-blocking.
- `pytest`: `31 passed`.
- `ruff check`: прошел.
- `git diff --check`: прошел; Git вывел только предупреждения о будущей CRLF-нормализации на Windows.

## Замечания по smoke-тесту

- Локальные порты `8444` в Windows оказались недоступны из-за системного port reservation, поэтому smoke-тест выполнен на `18081/18443`.
- Первый запуск API один раз поймал короткую гонку с Postgres. После этого добавлен retry в startup, повторный запуск API стал healthy без ручного вмешательства.
- Первый compose-проект `satelite` был остановлен и дочищен; активных smoke-контейнеров после проверки не осталось.

## Следующий шаг

Перед Phase 6 стоит решить, нужен ли перенос live analysis jobs из API executor в Redis/RQ/Celery worker. Это позволит сделать worker полноценным production-сервисом, переживать рестарты API и честно масштабировать долгие расчеты.
