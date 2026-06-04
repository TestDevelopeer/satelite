# Phase 2.2: Reference Scene Matching + Scene Selection Stabilization

Дата выполнения: 2026-06-03

## Цель

Стабилизировать выбор Sentinel-2 сцены для стандартных зон дипломной методики, чтобы публичный dashboard не выбирал сцену с низким покрытием зоны, если среди STAC-кандидатов есть сцена той же даты/тайла или более качественная альтернатива.

Этап не включает PDF, drawing tools, comparison mode, Docker, auth или production-функции.

## Reference matching

Для стандартных зон используются thesis reference scenes из `thesis-reference-results.json`:

- `sceneId`;
- `sceneDate`;
- MGRS tile, извлекаемый из thesis id;
- platform `S2A` / `S2B`, если она есть в id.

Earth Search STAC item id не обязан совпадать с thesis id буквально. Поэтому matching устойчивый:

- exact thesis id, если когда-нибудь STAC вернет тот же id;
- same date + same MGRS tile + compatible platform;
- same tile near reference date;
- alternative, если точная reference-связь не найдена.

## Candidate ranking

STAC search теперь берет до `80` candidates и ранжирует их по `selectionScore`.

Основные сигналы:

- lightweight estimated coverage через пересечение `item.geometry` с zone geometry;
- совпадение reference date + MGRS tile;
- совпадение reference tile;
- совпадение platform;
- близость даты к reference date;
- cloud cover.

Coverage получает самый высокий вес. Это исправляет ситуацию, где сцена с почти нулевой облачностью, но низким покрытием зоны, выбиралась раньше сцены с почти полным покрытием.

Для thesis zones действует guard:

- если выбранный candidate имеет estimated coverage `< 0.8`, но есть candidate с coverage `>= 0.95`, low-coverage candidate не выбирается;
- если хороших сцен нет, выбирается лучшая доступная и возвращается явное предупреждение.

## Result metadata

`GET /api/analyses/{analysisId}/result` теперь включает в `scene`:

- `thesisReferenceId`;
- `referenceDate`;
- `referenceTile`;
- `referenceMatchStatus`;
- `sceneSelectionReason`;
- `candidateCount`;
- `topCandidates`.

`referenceMatchStatus`:

- `exact_id`;
- `same_date_tile`;
- `same_tile_near_date`;
- `alternative`;
- `not_found`.

`topCandidates` содержит компактную сводку:

- `itemId`;
- `date`;
- `tile`;
- `platform`;
- `cloudCover`;
- `estimatedCoverage`;
- `selectionScore`;
- `referenceMatchStatus`.

## Verification

Для `rostov_on_don`, `2020`, период `2020-06-01` — `2020-09-15` выбран:

```text
S2B_T37TEN_20200719T081640_L2A
```

Результат:

- reference status: `same_date_tile`;
- selected date: `2020-07-19`;
- tile: `37TEN`;
- candidate count: `22`;
- estimated coverage top candidate: `1.0`;
- final raster coverage: `0.9999770176839016`;
- valid pixel ratio: `0.9999556203551204`.

До исправления UI мог выбрать:

```text
S2B_T37TEN_20200831T082605_L2A
```

с coverage около `15.7%`. После Phase 2.2 wide date range выбирает same-date/tile reference candidate с почти полным покрытием.

## Ограничения

- Ranking использует lightweight geometry coverage до финального raster read; full SCL/valid-pixel coverage считается после выбора сцены.
- `topCandidates` ограничен первыми 8 candidates, чтобы не раздувать response.
- Если STAC не возвращает хороших candidates для периода/лимита облачности, backend все равно выбирает лучшую доступную сцену и показывает предупреждение.
