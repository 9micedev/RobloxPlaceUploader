# RobloxPlaceUploader

Сценарий: **вставил cookie → залил `.rbxl` → получил ссылку → открылось в браузере**.

## Быстрый запуск

```bash
export ROBLOSECURITY='ВАШ_COOKIE'
python 11/main.py --file Place.rbxl
```

Что делает скрипт автоматически:
1. Получает `X-CSRF-TOKEN`.
2. Находит ваш аккаунт и список ваших игр.
3. Берёт `rootPlace.id` последней игры (или использует `--place-id`, если указан).
4. Загружает `.rbxl/.rbxlx` файл в place.
5. Пытается выставить universe в public.
6. Печатает ссылку и открывает её в браузере.

## Параметры

- `--cookie` — `.ROBLOSECURITY` (если не указан, используется `ROBLOSECURITY`).
- `--file` — путь к `.rbxl/.rbxlx` (по умолчанию `Place.rbxl`).
- `--place-id` — опционально: если не указать, place выбирается автоматически.
- `--no-open` — не открывать ссылку в браузере.
- `--timeout` — timeout HTTP (сек), по умолчанию `90`.
- `--retries` — число повторов при временных ошибках, по умолчанию `2`.

## Важное

Roblox объявил деприкацию upload через `data.roblox.com/Data/Upload.ashx` для place-трафика с `2024-06-24`.
Этот cookie-only сценарий работает как best-effort. Если Roblox блокирует этот путь на вашем аккаунте — используйте Open Cloud Place Publishing API.

## Безопасность

- Не передавайте `.ROBLOSECURITY` третьим лицам.
- Не коммитьте cookie в репозиторий.
