# Phase 7 — Demo Readiness, Portfolio Polish and Defense Walkthrough

## Цель

Подготовить GeoEco Monitor к защите диплома и portfolio-показу: улучшить первый экран, демо-сценарий, русские тексты UI, методическое объяснение, README и пошаговый walkthrough.

## Что реализовано

- В левую панель dashboard добавлен компактный intro-блок.
- Добавлен блок “Демо-сценарий” с кнопкой “Подготовить демо-сценарий”.
- Демо-кнопка выбирает Ростов-на-Дону, режим 2020 ↔ 2025 и не запускает live-расчет без явного подтверждения.
- Добавлены навигационные ссылки “Методика” и “О проекте”.
- Улучшены русские подписи:
  - “Parent analysis” заменен на “Сравнение”;
  - “Child job” заменен на “Дочерний расчет”;
  - “Summary” заменен на “Краткий итог”;
  - “Raw score” заменен на “Исходный балл”;
  - технический текст PDF/RQ сделан понятнее.
- Добавлена страница `/methodology`.
- Добавлена страница `/about`.
- Добавлен `docs/DEMO_WALKTHROUGH.md`.
- Добавлена папка `docs/screenshots/` со стабильными screenshot paths.
- README обновлен как portfolio README.

## Ключевые файлы

- `apps/web/components/dashboard.tsx`
- `apps/web/app/globals.css`
- `apps/web/app/methodology/page.tsx`
- `apps/web/app/about/page.tsx`
- `apps/web/tests/phase7.test.mjs`
- `docs/DEMO_WALKTHROUGH.md`
- `docs/screenshots/README.md`
- `README.md`

## Ограничения

- Phase 7 не добавляет drawing tools, auth, billing, user accounts или import/export GeoJSON.
- PDF status polling в UI пока не автоматизирован: frontend показывает queued/ready response после действия, а status endpoints уже доступны для следующего улучшения.
- Скриншоты в `docs/screenshots/` собраны из ранее сохраненных визуальных проверок; после публичного деплоя их стоит обновить свежими browser screenshots.

## Выполненные проверки

```powershell
npm --workspace apps/web run test
npm run lint
npm run build
apps\api\.venv\Scripts\python.exe -m pytest
apps\api\.venv\Scripts\python.exe -m ruff check
docker compose -f docker-compose.prod.yml config
git diff --check
```

Результаты:

- `npm --workspace apps/web run test`: `4 passed`.
- `npm run lint`: прошел.
- `npm run build`: прошел; Windows SWC warning остался non-blocking.
- `pytest`: `37 passed`.
- `ruff check`: прошел.
- `docker compose -f docker-compose.prod.yml config`: прошел.
- `git diff --check`: прошел; Git вывел только CRLF warnings.

## Ручная проверка

- `http://localhost:3000/`: HTTP `200`.
- `http://localhost:3000/methodology`: HTTP `200`.
- `http://localhost:3000/about`: HTTP `200`.
- Browser navigation открыл главную страницу.
- Кнопка “Подготовить демо-сценарий” выбирает Ростов-на-Дону и режим 2020 ↔ 2025.
- После подготовки появляется “Запустить сравнение”; live-расчет не стартует без явного клика пользователя.
- Страницы `/methodology` и `/about` открываются через browser navigation.

## Следующий шаг

Phase 8 лучше сделать как final QA + deploy на реальный VPS + публичная ссылка. После этого можно возвращаться к пользовательским зонам и drawing tools.
