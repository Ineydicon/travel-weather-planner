# Схема API - Travel Weather Planner

Базова адреса: `http://localhost:8000` (локально) або публічна адреса на Render.
Формат даних: JSON. Інтерактивна документація (Swagger UI) доступна після запуску за адресою **`/docs`**.

## Перелік ендпоінтів

| Метод | Шлях | Призначення |
|---|---|---|
| `GET` | `/` | Вебсторінка з формою прогнозу |
| `GET` | `/api/v1/health` | Перевірка стану сервісу |
| `GET` | `/api/v1/cities?name=Львів` | Пошук міста (Open-Meteo Geocoding) |
| `POST` | `/api/v1/plan` | Прогноз + статуси-попередження + чек-ліст |
| `POST` | `/api/v1/tick` | Планувальник розсилки (викликає GitHub Actions, заголовок `X-Cron-Secret`) |
| `POST` | `/telegram/webhook` | Приймання повідомлень від Telegram (заголовок `X-Telegram-Bot-Api-Secret-Token`) |

## Приклади

### `GET /api/v1/health`

```json
{ "status": "ok", "version": "1.0.0" }
```

### `POST /api/v1/plan`

Запит:

```json
{ "city": "Львів", "date_from": "2026-10-20", "date_to": "2026-10-22" }
```

Перевірка вхідних даних (інакше `422`): `date_to` не раніше за `date_from`, `date_from` не в минулому,
`date_to` не далі ніж 16 днів від сьогодні (межа прогнозу Open-Meteo).

Відповідь `200 OK`:

```json
{
  "city": { "name": "Львів", "country": "Україна", "region": "Львівська область",
            "latitude": 49.8383, "longitude": 24.0232, "timezone": "Europe/Kyiv" },
  "days": [
    { "day": "2026-10-20", "temp_min": 6.2, "temp_max": 14.8, "precipitation_sum": 3.4,
      "precipitation_probability": 70, "wind_speed_max": 8.1, "uv_index_max": 2.5, "weather_code": 61 }
  ],
  "alerts": [
    { "level": "warning", "text": "☔ Візьміть парасольку!" }
  ],
  "checklist": [
    { "category": "Одяг", "item": "Тепла куртка", "reason": "Мінімальна температура 6 °C" },
    { "category": "Аксесуари", "item": "Парасолька", "reason": "Ймовірність опадів до 70 %" }
  ]
}
```

Помилки: `404` - місто не знайдено; `502` - Open-Meteo недоступний або повернув некоректні дані.

### `POST /api/v1/tick`

Викликається за розкладом кожні 10 хв. Без правильного `X-Cron-Secret` - `403`.
Надсилає ранковий прогноз підписникам, у яких настала обрана година, і раз на годину перевіряє
небезпечну погоду. Відповідь: `{ "ok": true, "subscriptions": 3 }`.

### `POST /telegram/webhook`

Викликає сам Telegram. Без правильного секретного заголовка - `403`.
Команди бота: `/start`, `/help`, `/weather`, `/plan`, `/subscribe`, `/me`, `/unsubscribe`, `/simulate`.

## Звернення до зовнішніх API

| Сервіс | Запит |
|---|---|
| Open-Meteo Geocoding | `GET https://geocoding-api.open-meteo.com/v1/search?name=Львів&count=5&language=uk` |
| Open-Meteo Forecast | `GET https://api.open-meteo.com/v1/forecast?latitude=49.84&longitude=24.02&daily=temperature_2m_min,temperature_2m_max,precipitation_sum,precipitation_probability_max,wind_speed_10m_max,uv_index_max,weather_code&wind_speed_unit=ms&timezone=auto&start_date=2026-10-20&end_date=2026-10-23` |
| Telegram Bot API | `POST https://api.telegram.org/bot<TOKEN>/sendMessage` з тілом `{"chat_id": 123456789, "text": "..."}` |
