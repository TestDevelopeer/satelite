# GeoEco Monitor

GeoEco Monitor — публичный аналитический дашборд предварительной дистанционной оценки территории по спутниковым данным Sentinel-2 L2A.

Проект создается как MVP для портфолио и защиты дипломной работы “Оценка качества окружающей среды современными методами дистанционного зондирования”.

## Что есть в Phase 1

- Monorepo: Next.js frontend и FastAPI backend.
- Локальный запуск без Docker: `npm run dev`.
- Backend endpoints:
  - `GET /health`
  - `GET /api/zones/defaults`
  - `POST /api/analyses`
  - `GET /api/analyses/{analysisId}`
  - `GET /api/analyses/{analysisId}/result`
- Три стандартные bbox-зоны методики в `default-zones.geojson`.
- Reference fixtures диплома в `thesis-reference-results.json`.
- Live pipeline: STAC search, выбор Sentinel-2 сцены, поиск assets, rasterio-чтение окон, SCL mask, NDVI/NDWI/NDBI, статистика, scoring.
- Dashboard shell: выбор зоны/года, запуск расчета, статус, карта bbox, метаданные сцены, индексы, класс, интерпретация и ограничения метода.

## Требования

- Node.js 20+
- Python 3.11 x64
- Windows PowerShell или совместимая оболочка

Docker для локальной разработки не требуется и будет использоваться только для production/VPS в следующих этапах.

## Локальный запуск

```powershell
npm install
npm run dev
```

Frontend: <http://localhost:3000>  
Backend: <http://localhost:8000>

`npm run dev` создает `apps/api/.venv`, устанавливает backend-зависимости и запускает оба сервера.

## Если не установился rasterio/GDAL на Windows

Live raster pipeline зависит от `rasterio`. Если установка падает:

1. Проверьте, что установлен Python 3.11 x64.
2. Обновите pip:

```powershell
apps\api\.venv\Scripts\python.exe -m pip install --upgrade pip
```

3. Повторите установку:

```powershell
apps\api\.venv\Scripts\pip.exe install -r apps\api\requirements.txt
```

Если wheel для вашей среды недоступен, используйте production Docker на VPS после Phase 2/3. Phase 1 честно остановится с понятной ошибкой, потому что без rasterio/GDAL live Sentinel-2 расчет невозможен.

## Проверки

```powershell
npm run lint
npm run build
pytest
ruff check
```

## Как проверить live analysis локально

1. Запустите dev-серверы:

```powershell
npm run dev
```

2. В отдельном PowerShell проверьте backend:

```powershell
Invoke-RestMethod http://localhost:8000/health
```

3. Запустите минимальный live-расчет для Ростова-на-Дону за 2020 год:

```powershell
@'
import json, time, requests

payload = {
    "zoneSlug": "rostov_on_don",
    "zoneName": "Ростов-на-Дону",
    "geometry": {
        "type": "Polygon",
        "coordinates": [[[39.58, 47.11], [39.82, 47.11], [39.82, 47.36], [39.58, 47.36], [39.58, 47.11]]]
    },
    "year": 2020,
    "dateRange": {"start": "2020-07-01", "end": "2020-08-15"},
    "mode": "single",
    "cloudCoverMax": 20,
    "isCustomZone": False
}

created = requests.post("http://localhost:8000/api/analyses", json=payload, timeout=30)
created.raise_for_status()
analysis_id = created.json()["analysisId"]

while True:
    job = requests.get(f"http://localhost:8000/api/analyses/{analysis_id}", timeout=20).json()
    print(job["status"], job["progress"], job["stage"])
    if job["status"] in {"succeeded", "failed"}:
        print(json.dumps(job, ensure_ascii=False, indent=2))
        break
    time.sleep(3)

if job["status"] == "succeeded":
    result = requests.get(f"http://localhost:8000/api/analyses/{analysis_id}/result", timeout=20)
    print(json.dumps(result.json(), ensure_ascii=False, indent=2))
'@ | apps\api\.venv\Scripts\python.exe -
```

4. Успешный расчет должен пройти этапы поиска STAC-кандидатов, выбора сцены, чтения каналов, SCL mask, расчета NDVI/NDWI/NDBI и вернуть `stats`.

## Как проверить raster layers локально

Raster layers появляются только после успешного live analysis. Они не строятся из thesis fixtures.

После завершения расчета backend сохраняет GeoTIFF outputs в:

```text
data/rasters/{analysisId}/rgb.tif
data/rasters/{analysisId}/ndvi.tif
data/rasters/{analysisId}/ndwi.tif
data/rasters/{analysisId}/ndbi.tif
```

`GET /api/analyses/{analysisId}/result` возвращает массив `rasterLayers`:

- `layer`;
- `path`;
- `min`;
- `max`;
- `nodata`;
- `crs`;
- `bounds`;
- `tileUrl`.

Tile endpoint:

```text
GET /api/tiles/{analysisId}/{layer}/{z}/{x}/{y}.png
```

Поддерживаемые значения `layer`:

- `rgb`;
- `ndvi`;
- `ndwi`;
- `ndbi`.

Индексные тайлы цветизуются на backend со стабильными диапазонами:

- NDVI: `-0.2` to `0.8`;
- NDWI: `-0.5` to `0.6`;
- NDBI: `-0.6` to `0.6`.

На dashboard после успешного расчета можно переключать RGB / NDVI / NDWI / NDBI и менять прозрачность слоя.

## Методическое ограничение

Результаты являются предварительной дистанционной оценкой по спутниковым данным Sentinel-2 и не заменяют лабораторные измерения, санитарно-гигиеническую экспертизу и натурное обследование.

Приложение не формирует санитарное заключение, не доказывает загрязнение и не присваивает официальный нормативный класс.
