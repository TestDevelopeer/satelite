# Phase 6 — Redis/RQ Worker Queue for Production Jobs

## Цель

Вынести тяжелые production-задачи из FastAPI request thread в Redis/RQ worker architecture. API должен быстро создавать запись расчета или отчета, ставить задачу в очередь и возвращать id/status. Worker выполняет live Sentinel-2 processing, comparison и PDF generation отдельно от API.

## Выбор очереди

Выбран RQ, а не Celery.

Причина: текущему MVP нужна простая Redis-backed очередь без сложной маршрутизации, отдельного result backend и большого набора Celery-настроек. RQ достаточно для production-сценария GeoEco Monitor: один queue name, несколько worker-процессов через Docker scale, явные timeout-ы и понятные логи.

## Что реализовано

- Добавлены зависимости `redis` и `rq`.
- Добавлен режим выполнения:
  - `JOB_EXECUTION_MODE=in_process` для обычной локальной разработки;
  - `JOB_EXECUTION_MODE=rq` для production/VPS.
- Добавлен диспетчер `app.services.job_queue`, который ставит задачи либо в локальный executor, либо в Redis/RQ.
- Добавлен worker entrypoint:

```text
python -m app.worker
```

- Добавлены worker tasks:
  - `run_analysis_job_task(analysis_id, cloud_cover_max)`;
  - `run_comparison_job_task(comparison_id, cloud_cover_max)`;
  - `generate_analysis_report_task(report_job_id, analysis_id)`;
  - `generate_comparison_report_task(report_job_id, comparison_id)`.
- Production `docker-compose.prod.yml` теперь запускает worker по умолчанию.
- API в production получает `JOB_EXECUTION_MODE=rq`, поэтому не считает heavy jobs внутри request thread.
- Добавлена модель `ReportJob` для persisted PDF status:
  - `pending`;
  - `queued`;
  - `generating`;
  - `ready`;
  - `failed`.
- Добавлены status endpoints:
  - `GET /api/reports/analysis/{analysisId}/status`;
  - `GET /api/reports/comparison/{comparisonId}/status`.
- PDF endpoints теперь в `rq` режиме возвращают queued report status, а PDF генерируется worker-ом.
- Frontend не показывает ссылку скачивания PDF, пока report status не `ready`.

## API behavior

В `rq` режиме:

- `POST /api/analyses` создает `AnalysisJob(status=queued)`, кладет RQ task и возвращает `analysisId`.
- `POST /api/comparisons` создает parent `ComparisonJob` и два child `AnalysisJob`, кладет parent task и возвращает `comparisonId`.
- `POST /api/reports/analysis/{analysisId}` создает/обновляет `ReportJob(status=queued)`, кладет PDF task и возвращает status.
- `POST /api/reports/comparison/{comparisonId}` работает аналогично для comparison report.

Если Redis недоступен, API возвращает понятную ошибку. Если queue заполнена по `QUEUE_MAX_JOBS`, API возвращает ошибку перегрузки.

## Env variables

```text
JOB_EXECUTION_MODE=in_process|rq
REDIS_URL=redis://redis:6379/0
QUEUE_NAME=geoeco
QUEUE_MAX_JOBS=20
WORKER_CONCURRENCY=1
RQ_DEFAULT_TIMEOUT=3600
RQ_ANALYSIS_TIMEOUT=3600
RQ_COMPARISON_TIMEOUT=7200
RQ_REPORT_TIMEOUT=1200
```

`WORKER_CONCURRENCY` документирует целевое число worker-процессов. На практике RQ масштабируется через Docker:

```bash
docker compose --env-file .env.production -f docker-compose.prod.yml up -d --scale worker=2
```

## Docker changes

- `worker` больше не reserved profile.
- `worker` использует тот же API image и команду `python -m app.worker`.
- `api` и `worker` используют одинаковые production env и storage volumes:
  - `/data/rasters`;
  - `/data/reports`;
  - `/data/cache`;
  - `/data/logs`.
- `api` зависит от Postgres/Redis.
- `worker` зависит от Postgres/Redis.

## Локальная разработка

Обычная Windows-разработка не требует Redis:

```powershell
npm run dev
```

По умолчанию:

```text
JOB_EXECUTION_MODE=in_process
```

Для локальной проверки RQ можно поднять Redis отдельно и запустить backend с:

```powershell
$env:JOB_EXECUTION_MODE="rq"
$env:REDIS_URL="redis://localhost:6379/0"
apps\api\.venv\Scripts\python.exe -m app.worker
```

## Troubleshooting

Redis unavailable:

- проверить `REDIS_URL`;
- проверить `docker compose ps redis`;
- посмотреть `docker compose logs redis`.

Worker не обрабатывает jobs:

- проверить `docker compose logs -f worker`;
- проверить `rq info -u "$REDIS_URL"`;
- убедиться, что API и worker используют один `QUEUE_NAME`.

Job stuck queued:

- проверить, что worker запущен;
- проверить queue length;
- проверить, не превышен ли timeout;
- перезапустить worker.

Timeout:

- увеличить `RQ_ANALYSIS_TIMEOUT`, `RQ_COMPARISON_TIMEOUT` или `RQ_REPORT_TIMEOUT`;
- проверить покрытие зоны, cloud mask и STAC asset access.

Storage volume permission issue:

- проверить, что `api` и `worker` монтируют одни и те же volumes;
- проверить `/data/rasters`, `/data/reports`, `/data/cache`;
- перезапустить контейнеры после исправления прав.

## Проверки этапа

Добавлены tests без реального Redis:

- enqueue behavior в `rq` mode через fake queue;
- `in_process` dispatch остается доступным;
- worker task вызывает runner;
- report status response;
- queue overload error.

Выполненные команды:

```powershell
apps\api\.venv\Scripts\python.exe -m pip install -r apps\api\requirements.txt
npm run lint
npm run build
apps\api\.venv\Scripts\python.exe -m pytest
apps\api\.venv\Scripts\python.exe -m ruff check
docker compose -f docker-compose.prod.yml config
docker compose -f docker-compose.prod.yml build
$env:HTTP_PORT="18082"; $env:HTTPS_PORT="18445"; $env:PUBLIC_DOMAIN=":80"; docker compose -p geoeco_phase6 -f docker-compose.prod.yml up -d
curl http://localhost:18082/health
docker compose -p geoeco_phase6 -f docker-compose.prod.yml logs --tail=80 worker
docker compose -p geoeco_phase6 -f docker-compose.prod.yml exec -T api python -c "from redis import Redis; from rq import Queue; q=Queue('geoeco', connection=Redis.from_url('redis://redis:6379/0')); job=q.enqueue('app.worker_tasks.run_analysis_job_task', 'smoke-missing-analysis', 20, job_timeout=60); print(job.id)"
docker compose -p geoeco_phase6 -f docker-compose.prod.yml exec -T api rq info -u redis://redis:6379/0
docker compose -p geoeco_phase6 -f docker-compose.prod.yml down
```

Результаты:

- `npm run lint`: прошел.
- `npm run build`: прошел; Windows SWC warning остался non-blocking.
- `pytest`: `37 passed`.
- `ruff check`: прошел.
- `docker compose -f docker-compose.prod.yml config`: прошел.
- `docker compose -f docker-compose.prod.yml build`: прошел.
- Production smoke через Caddy: `/health` вернул `{"status":"ok","service":"geoeco-api"}`.
- Worker log: `GeoEco RQ worker listening on queue 'geoeco'`.
- Safe RQ smoke job: `e69bf37e-4598-4de5-9666-20e4b8d41c3c`.
- Worker обработал smoke job: `Successfully completed app.worker_tasks.run_analysis_job_task('smoke-missing-analysis', 20)`.
- `rq info`: `0 jobs total`, `1 finished`, `0 failed`, worker idle.

## Ограничения

- Comparison parent task пока выполняет child analysis jobs последовательно внутри worker. Это production-safe относительно API, но еще не полноценный parallel fan-out/fan-in.
- RQ job results не используются как источник данных; источником правды остается DB.
- Production миграции БД все еще не добавлены отдельным инструментом.

## Следующий шаг

Для Phase 7 лучше выбрать финальную полировку демонстрационного сценария: UI/landing/portfolio case page, стабильный walkthrough для защиты диплома, подготовленные screenshots и короткая инструкция запуска. Drawing tools можно делать позже, когда production reliability уже закреплена.
