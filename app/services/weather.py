"""Клієнт Open-Meteo (API 1): пошук міста та прогноз погоди.

Ключ API не потрібен. Усі запити обгорнуті в обробку помилок:
мережеві збої, тайм-аути та статуси, відмінні від 200, перетворюються
на WeatherServiceError із зрозумілим повідомленням.
"""
import time
from datetime import date

import httpx

from app.schemas import City, DayForecast

GEOCODING_URL = "https://geocoding-api.open-meteo.com/v1/search"
FORECAST_URL = "https://api.open-meteo.com/v1/forecast"
TIMEOUT = httpx.Timeout(10.0)

DAILY_FIELDS = [
    "temperature_2m_min",
    "temperature_2m_max",
    "precipitation_sum",
    "precipitation_probability_max",
    "wind_speed_10m_max",
    "uv_index_max",
    "weather_code",
]


CACHE_TTL_SECONDS = 30 * 60  # не частіше ніж раз на 30 хв для одного міста/дат
_cache: dict[tuple, tuple[float, object]] = {}


def _cache_get(key: tuple):
    hit = _cache.get(key)
    if hit and time.monotonic() - hit[0] < CACHE_TTL_SECONDS:
        return hit[1]
    return None


def _cache_set(key: tuple, value) -> None:
    _cache[key] = (time.monotonic(), value)


class WeatherServiceError(Exception):
    """Open-Meteo недоступний або повернув помилку."""


class CityNotFoundError(WeatherServiceError):
    """Місто з такою назвою не знайдено."""


async def _get_json(client: httpx.AsyncClient, url: str, params: dict) -> dict:
    try:
        response = await client.get(url, params=params)
    except httpx.TimeoutException:
        raise WeatherServiceError("Open-Meteo не відповідає (тайм-аут). Спробуйте пізніше.")
    except httpx.RequestError as e:
        raise WeatherServiceError(f"Немає з'єднання з Open-Meteo ({type(e).__name__}). "
                                  "Перевірте інтернет.")

    if response.status_code == 429:
        raise WeatherServiceError("Перевищено ліміт запитів до Open-Meteo. Спробуйте пізніше.")
    if response.status_code != 200:
        try:
            reason = response.json().get("reason", "")
        except ValueError:
            reason = response.text[:200]
        raise WeatherServiceError(f"Open-Meteo повернув помилку {response.status_code}: {reason}")

    try:
        return response.json()
    except ValueError:
        raise WeatherServiceError("Open-Meteo повернув некоректну відповідь (не JSON).")


async def search_cities(name: str, count: int = 5,
                        client: httpx.AsyncClient | None = None) -> list[City]:
    """Повертає список міст за назвою. Якщо нічого не знайдено — CityNotFoundError."""
    key = ("city", name.strip().lower(), count)
    if client is None and (cached := _cache_get(key)) is not None:
        return cached

    params = {"name": name, "count": count, "language": "uk", "format": "json"}
    async with _client(client) as c:
        data = await _get_json(c, GEOCODING_URL, params)

    results = data.get("results") or []
    if not results:
        raise CityNotFoundError(f"Місто «{name}» не знайдено. Перевірте назву.")

    cities = [
        City(
            name=r["name"],
            country=r.get("country", ""),
            region=r.get("admin1"),
            latitude=r["latitude"],
            longitude=r["longitude"],
            timezone=r.get("timezone", "auto"),
        )
        for r in results
    ]
    _cache_set(key, cities)
    return cities


async def get_forecast(city: City, date_from: date, date_to: date,
                       client: httpx.AsyncClient | None = None) -> list[DayForecast]:
    """Повертає щоденний прогноз для міста на вказані дати (з кешем на 30 хв)."""
    key = ("forecast", round(city.latitude, 2), round(city.longitude, 2), date_from, date_to)
    if client is None and (cached := _cache_get(key)) is not None:
        return cached

    params = {
        "latitude": city.latitude,
        "longitude": city.longitude,
        "daily": ",".join(DAILY_FIELDS),
        "wind_speed_unit": "ms",
        "timezone": "auto",
        "start_date": date_from.isoformat(),
        "end_date": date_to.isoformat(),
    }
    async with _client(client) as c:
        data = await _get_json(c, FORECAST_URL, params)

    daily = data.get("daily")
    if not daily or "time" not in daily:
        raise WeatherServiceError("Відповідь Open-Meteo не містить щоденного прогнозу.")

    def value(field: str, i: int, default: float = 0):
        v = daily.get(field, [None] * len(daily["time"]))[i]
        return default if v is None else v

    days = [
        DayForecast(
            day=day,
            temp_min=value("temperature_2m_min", i),
            temp_max=value("temperature_2m_max", i),
            precipitation_sum=value("precipitation_sum", i),
            precipitation_probability=int(value("precipitation_probability_max", i)),
            wind_speed_max=value("wind_speed_10m_max", i),
            uv_index_max=value("uv_index_max", i),
            weather_code=int(value("weather_code", i)),
        )
        for i, day in enumerate(daily["time"])
    ]
    _cache_set(key, days)
    return days


class _client:
    """Використовує переданий клієнт (для тестів) або створює новий."""

    def __init__(self, client: httpx.AsyncClient | None):
        self._external = client
        self._own: httpx.AsyncClient | None = None

    async def __aenter__(self) -> httpx.AsyncClient:
        if self._external is not None:
            return self._external
        self._own = httpx.AsyncClient(timeout=TIMEOUT)
        return self._own

    async def __aexit__(self, *exc):
        if self._own is not None:
            await self._own.aclose()
