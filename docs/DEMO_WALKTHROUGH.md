# Demo Walkthrough — GeoEco Monitor

## Цель демонстрации

Показать за 3-5 минут, что GeoEco Monitor является рабочим публичным аналитическим дашбордом: он берет live Sentinel-2 L2A данные, считает NDVI/NDWI/NDBI, показывает карту анализа, сравнение 2020 ↔ 2025, качество данных и формирует PDF-отчет.

## Локальный запуск

```powershell
cd D:\domains\satelite
nvm use 20.19.0
npm install
npm run dev
```

Открыть:

```text
http://localhost:3000
```

Backend:

```text
http://localhost:8000/health
```

Обычная локальная разработка работает без Docker. Production/VPS использует Docker, PostGIS, Redis и RQ worker.

## Сценарий защиты

1. Открыть главную страницу.
   - Сказать: “Это публичный аналитический дашборд предварительной дистанционной оценки по Sentinel-2 L2A.”

2. Открыть страницу “Методика”.
   - Показать, что используются NDVI, NDWI, NDBI.
   - Отдельно проговорить: “Результат не является лабораторным измерением или официальным экологическим заключением.”

3. Вернуться к панели мониторинга.
   - Нажать “Подготовить демо-сценарий”.
   - Проверить, что выбраны “Ростов-на-Дону” и режим “2020 ↔ 2025”.

4. Нажать “Запустить сравнение”.
   - Сказать: “Создается parent comparison job и два дочерних live-расчета: 2020 и 2025.”

5. Показать статусы.
   - Обратить внимание на этапы: поиск STAC-кандидатов, выбор сцены, чтение каналов, SCL mask, расчет индексов, сохранение растров.

6. После завершения показать карту.
   - Переключить RGB, NDVI и NDBI.
   - Сказать: “Слои построены из live-расчета, а не из reference fixtures.”

7. Показать блок “Качество данных”.
   - Объяснить покрытие зоны, валидные пиксели, cloud/SCL mask и nodata.

8. Показать таблицу изменений.
   - Объяснить изменение NDVI, NDWI, NDBI, normalized score и итогового предварительного класса.

9. Нажать “Сформировать PDF сравнения”.
   - В local mode PDF может сформироваться сразу.
   - В production mode PDF ставится в Redis/RQ очередь и формируется worker-ом.

10. Скачать PDF.
    - PDF сохраняется в:

```text
data/reports/analysis/
data/reports/comparison/
```

11. Завершить демонстрацию disclaimer-ом.
    - Сказать: “Это предварительная дистанционная оценка, она показывает зоны внимания и требует проверки натурными и лабораторными данными.”

## Если STAC долго отвечает

- Не перезапускать страницу сразу: live Sentinel-2 расчет может занимать несколько минут.
- Проверить статус job в правой панели.
- Проверить backend logs.
- Если STAC недоступен, UI должен показать честную ошибку.

## Если очередь занята

В production RQ mode API вернет ошибку перегрузки очереди, если достигнут `QUEUE_MAX_JOBS`.

Что делать:

```bash
docker compose --env-file .env.production -f docker-compose.prod.yml logs -f worker
docker compose --env-file .env.production -f docker-compose.prod.yml exec worker rq info -u "$REDIS_URL"
docker compose --env-file .env.production -f docker-compose.prod.yml up -d --scale worker=2
```

## Что показать работодателю

- Полный стек: Next.js, FastAPI, rasterio, MapLibre, PostGIS, Redis/RQ, Docker/Caddy, Playwright PDF.
- Архитектуру API/worker: API не блокирует request thread тяжелыми расчетами в production.
- Честность методики: fixtures не подменяют live result, warnings показывают качество данных.
- Реальный PDF, а не заглушку.
