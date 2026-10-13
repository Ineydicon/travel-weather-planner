# Схема API — Travel Weather Planner

Базова адреса: `http://localhost:8000` (локально).
Формат даних: JSON. Інтерактивна документація (Swagger UI) доступна після запуску за адресою **`/docs`**.

## Перелік ендпоінтів

| Метод | Шлях | Призначення | Статус |
|---|---|---|---|
| `GET` | `/api/v1/health` | Перевірка стану сервісу | ✅ Працює |
| `GET` | `/api/v1/cities?name=Львів` | Пошук міста (Open-Meteo Geocoding) | День 3 |
| `POST` | `/api/v1/plan` | Прогноз погоди + чек-ліст для поїздки | День 3 |
| `GET` | `/api/v1/trips/{trip_id}` | Отримати збережену поїздку | День 3 |
| `POST` | `/api/v1/trips/{trip_id}/send` | Надіслати чек-ліст у Telegram | День 4 |
| `POST` | `/telegram/webhook` | Приймання повідомлень від Telegram | День 4 |

## Приклади

### `GET /api/v1/health`

```json
{ "status": "ok", "version": "0.1.0" }
```

### `GET /api/v1/cities?name=Львів`

```json
[
  {
    "name": "Львів",
    "country": "Україна",
    "region": "Львівська область",
    "latitude": 49.8383,
    "longitude": 24.0232,
    "timezone": "Europe/Kyiv"
  }
]
```

### `POST /api/v1/plan`

Запит:

```json
{ "city": "Львів", "date_from": "2026-10-20", "date_to": "2026-10-23" }
```

Правила перевірки (інакше `422 Unprocessable Entity`):
- `date_to` не раніше за `date_from`;
- `date_from` не в минулому;
- `date_to` не далі ніж 16 днів від сьогодні (межа прогнозу Open-Meteo).

Відповідь `200 OK`:

```json
{
  "trip_id": "3f9c2a1e-7b4d-4c8e-9a51-2d6f0b8e1c33",
  "city": { "name": "Львів", "country": "Україна", "region": "Львівська область",
            "latitude": 49.8383, "longitude": 24.0232, "timezone": "Europe/Kyiv" },
  "days": [
    {
      "day": "2026-10-20",
      "temp_min": 6.2,
      "temp_max": 14.8,
      "precipitation_sum": 3.4,
      "precipitation_probability": 70,
      "wind_speed_max": 8.1,
      "uv_index_max": 2.5,
      "weather_code": 61
    }
  ],
  "checklist": [
    { "category": "Одяг", "item": "Тепла куртка", "reason": "Мінімальна температура 6 °C" },
    { "category": "Аксесуари", "item": "Парасолька", "reason": "Ймовірність дощу 70 %" },
    { "category": "Документи", "item": "Паспорт / ID-картка", "reason": "Завжди" }
  ]
}
```

Помилки: `404` — місто не знайдено; `502` — Open-Meteo недоступний.

### `POST /api/v1/trips/{trip_id}/send`

Запит (свій `chat_id` користувач отримує від бота у відповідь на `/start`):

```json
{ "chat_id": 123456789 }
```

Відповідь: `{ "sent": true }`

### `POST /telegram/webhook`

Викликає сам Telegram. Запит повинен містити заголовок `X-Telegram-Bot-Api-Secret-Token`, рівний `TELEGRAM_WEBHOOK_SECRET`, інакше відповідь `403`.

Команди бота: `/start` (привітання + `chat_id`), `/help`, `/plan Львів 2026-10-20 2026-10-23`.

## Звернення до зовнішніх API

| Сервіс | Запит |
|---|---|
| Open-Meteo Geocoding | `GET https://geocoding-api.open-meteo.com/v1/search?name=Львів&count=5&language=uk` |
| Open-Meteo Forecast | `GET https://api.open-meteo.com/v1/forecast?latitude=49.84&longitude=24.02&daily=temperature_2m_min,temperature_2m_max,precipitation_sum,precipitation_probability_max,wind_speed_10m_max,uv_index_max,weather_code&wind_speed_unit=ms&timezone=auto&start_date=2026-10-20&end_date=2026-10-23` |
| Telegram Bot API | `POST https://api.telegram.org/bot<TOKEN>/sendMessage` з тілом `{"chat_id": 123456789, "text": "..."}` |
