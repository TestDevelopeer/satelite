# Локальный запуск после установки Python 3.11

Дата выполнения: 2026-06-03

## Цель

Добиться, чтобы локальная разработка запускалась через `npm run dev`:

- frontend на `http://localhost:3000`;
- backend на `http://localhost:8000`;
- `GET /health` возвращает нормальный ответ.

## Что сделано

- Проверена папка `C:\Users\User\Downloads\Python-3.11.15`.
- Установлено, что в ней находится исходный код CPython, а не Windows installer.
- Через `winget` найден установленный пакет `Python.Python.3.11`, но установка была неполной: отсутствовал основной `python.exe`.
- Найден кэшированный официальный installer:
  `C:\Users\User\AppData\Local\Package Cache\{1da2e09b-199c-4def-9a99-93a8c1b8ddf2}\python-3.11.9-amd64.exe`.
- Выполнен repair installer.
- Проверка `py -3.11 --version` успешно вернула `Python 3.11.9`.
- Удалена старая `apps/api/.venv`.
- Запущен `npm run dev`.
- Создана новая venv на Python 3.11.
- Установлены backend-зависимости, включая `rasterio`.

## Проверки

- `py -3.11 --version`:
  - результат: `Python 3.11.9`.
- `http://localhost:8000/health`:
  - результат: `{"status":"ok","service":"geoeco-api"}`.
- `http://localhost:3000`:
  - HTTP status: `200`;
  - страница содержит `GeoEco Monitor`.

## Предупреждения

- Next.js продолжает показывать warning о native SWC DLL:
  `Attempted to load @next/swc-win32-x64-msvc`.
- Это не заблокировало запуск frontend: Next.js использовал fallback и страница открылась.

## Текущее состояние

Dev-серверы оставлены запущенными:

- frontend: `http://localhost:3000`;
- backend: `http://localhost:8000`.
