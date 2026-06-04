# Phase 8 — Final QA + Real VPS Deploy + Public Link

Дата: 04.06.2026

## Цель

Провести финальную локальную проверку release candidate, проверить production Docker stack, подготовить документацию релиза и оценить готовность к VPS deployment.

## Что реализовано и проверено

- Добавлен production hardening для CORS через `CORS_ALLOWED_ORIGINS`.
- `MAX_DATE_RANGE_DAYS` поддержан как alias к backend-настройке `max_analysis_days`.
- PDF download endpoints защищены от unsafe id/path traversal.
- Создан release-candidate документ: `docs/RELEASE_CANDIDATE.md`.
- Проведен локальный production Docker smoke через Caddy на нестандартных портах `18083/18446`.
- Проверены API, frontend, methodology/about страницы, worker, Redis queue, `rasterio` и Playwright Chromium внутри контейнеров.
- Временный `.env.production` после smoke-теста удален.

## Команды и результаты

- `npm run lint` — прошло.
- `npm --workspace apps/web run test` — прошло, 4 теста.
- `apps\api\.venv\Scripts\python.exe -m pytest` — прошло, 38 тестов.
- `apps\api\.venv\Scripts\python.exe -m ruff check` — прошло.
- `npm run build` — прошло; остался не блокирующий Windows SWC warning.
- `docker compose -f docker-compose.prod.yml config` — прошло.
- `docker compose --env-file .env.production -f docker-compose.prod.yml build` — прошло.
- `docker compose -p geoeco_phase8 --env-file .env.production -f docker-compose.prod.yml up -d` — прошло.
- `Invoke-WebRequest http://localhost:18083/health` — прошло.
- `Invoke-WebRequest http://localhost:18083/` — HTTP 200.
- `Invoke-WebRequest http://localhost:18083/methodology` — HTTP 200.
- `Invoke-WebRequest http://localhost:18083/about` — HTTP 200.
- `docker compose ... exec api python -c "import rasterio; print(rasterio.__version__)"` — прошло, `1.4.3`.
- `docker compose ... exec api python -c "... chromium.launch(...)"` — прошло, `chromium_ok`.
- `rq info -u redis://redis:6379/0` — worker доступен, очередь `geoeco` слушается.
- RQ smoke job `38d4e030-7849-4b49-9008-05dbefd6adc3` — обработан worker-ом, 1 finished, 0 failed.
- `git diff --check` — прошло с CRLF normalization warnings на Windows.
- `npm audit --audit-level=moderate` — не прошло: 2 moderate warnings в `next/postcss`; auto-fix не применен, потому что предлагает неподходящий переход версии Next.js.

## Security sanity

- Закоммиченных `.env` или `.env.production` файлов не найдено.
- Найденные строки `POSTGRES_PASSWORD`, `DATABASE_URL`, `REDIS_URL` находятся в примерах, документации и Docker defaults.
- Публичных debug/smoke endpoints в backend не найдено.
- Production CORS настраивается exact origins, wildcard не используется.

## VPS deploy

Real VPS deploy не выполнен: в локальном окружении нет IP/domain/SSH credentials.

Публичный URL: не получен.

DNS/domain status: не проверялся, потому что домен и VPS не предоставлены.

VPS specs: неизвестны.

## Ограничения перед Phase 9 или публичным релизом

- Нужно предоставить VPS IP, SSH user/key, domain и DNS A record.
- Нужно заполнить `.env.production` реальными значениями `PUBLIC_DOMAIN`, `POSTGRES_PASSWORD`, `DATABASE_URL`, `CORS_ALLOWED_ORIGINS`.
- Нужно выполнить `DEPLOY_VPS.md` на сервере и провести public smoke test.
- Нужно повторно проверить live Sentinel-2 calculation и PDF generation уже на VPS.
- Нужно принять решение по `npm audit` warning после проверки совместимой версии Next.js.

## Следующий шаг

Выполнить реальный VPS deployment по `DEPLOY_VPS.md`, затем обновить `docs/RELEASE_CANDIDATE.md` публичной ссылкой и результатами public smoke test.
