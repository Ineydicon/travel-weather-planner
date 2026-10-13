"""Тести модулів інтеграції. Зовнішні API підмінюються (httpx.MockTransport),
тому тести не потребують інтернету і не витрачають ліміти."""
import asyncio
from datetime import date

import httpx
import pytest

from app.schemas import City, DayForecast
from app.services.formatter import format_plan_message
from app.services.notifier import TelegramError, send_message
from app.services.packing import build_checklist
from app.services.weather import (CityNotFoundError, WeatherServiceError, get_forecast,
                                  search_cities)

CITY = City(name="Кропивницький", country="Україна", region="Кіровоградська область",
            latitude=48.51, longitude=32.27, timezone="Europe/Kyiv")


def mock_client(handler) -> httpx.AsyncClient:
    return httpx.AsyncClient(transport=httpx.MockTransport(handler))


def day(**kw) -> DayForecast:
    base = dict(day=date(2026, 10, 15), temp_min=12, temp_max=18, precipitation_sum=0,
                precipitation_probability=0, wind_speed_max=3, uv_index_max=2, weather_code=0)
    base.update(kw)
    return DayForecast(**base)


# ---------- Open-Meteo ----------

def test_search_city_ok():
    def handler(request):
        assert request.url.params["name"] == "Кропивницький"
        return httpx.Response(200, json={"results": [{
            "name": "Кропивницький", "country": "Україна", "admin1": "Кіровоградська область",
            "latitude": 48.50834, "longitude": 32.26618, "timezone": "Europe/Kyiv"}]})
    cities = asyncio.run(search_cities("Кропивницький", client=mock_client(handler)))
    assert cities[0].name == "Кропивницький"
    assert cities[0].region == "Кіровоградська область"


def test_search_city_not_found():
    handler = lambda request: httpx.Response(200, json={"generationtime_ms": 0.5})
    with pytest.raises(CityNotFoundError):
        asyncio.run(search_cities("Qwertyzxc", client=mock_client(handler)))


def test_forecast_ok():
    def handler(request):
        return httpx.Response(200, json={"daily": {
            "time": ["2026-10-15", "2026-10-16"],
            "temperature_2m_min": [5.1, 3.0], "temperature_2m_max": [14.2, 11.0],
            "precipitation_sum": [0.0, 4.2], "precipitation_probability_max": [10, None],
            "wind_speed_10m_max": [4.0, 7.5], "uv_index_max": [3.1, 2.0],
            "weather_code": [2, 63]}})
    days = asyncio.run(get_forecast(CITY, date(2026, 10, 15), date(2026, 10, 16),
                                    client=mock_client(handler)))
    assert len(days) == 2
    assert days[1].precipitation_probability == 0  # None -> 0
    assert days[1].weather_code == 63


def test_forecast_server_error_is_handled():
    handler = lambda request: httpx.Response(500, json={"reason": "Internal error"})
    with pytest.raises(WeatherServiceError, match="500"):
        asyncio.run(get_forecast(CITY, date(2026, 10, 15), date(2026, 10, 16),
                                 client=mock_client(handler)))


def test_network_error_is_handled():
    def handler(request):
        raise httpx.ConnectError("no internet")
    with pytest.raises(WeatherServiceError, match="з'єднання"):
        asyncio.run(search_cities("Львів", client=mock_client(handler)))


def test_rate_limit_is_handled():
    handler = lambda request: httpx.Response(429, json={"reason": "Too many requests"})
    with pytest.raises(WeatherServiceError, match="ліміт"):
        asyncio.run(search_cities("Львів", client=mock_client(handler)))


# ---------- Telegram ----------

def test_telegram_send_ok():
    def handler(request):
        assert request.url.path.endswith("/sendMessage")
        return httpx.Response(200, json={"ok": True, "result": {"message_id": 1}})
    asyncio.run(send_message("TOKEN", 123, "hello", client=mock_client(handler)))


def test_telegram_bad_token():
    handler = lambda request: httpx.Response(401, json={"ok": False, "description": "Unauthorized"})
    with pytest.raises(TelegramError, match="токен") as e:
        asyncio.run(send_message("SECRET123", 123, "hi", client=mock_client(handler)))
    assert "SECRET123" not in str(e.value)  # токен не потрапляє в повідомлення


def test_telegram_chat_not_found():
    handler = lambda request: httpx.Response(
        400, json={"ok": False, "description": "Bad Request: chat not found"})
    with pytest.raises(TelegramError, match="/start"):
        asyncio.run(send_message("T", 1, "hi", client=mock_client(handler)))


# ---------- Обробка даних ----------

def test_checklist_rain_and_cold():
    items = {i.item for i in build_checklist([day(temp_min=4, precipitation_probability=80)])}
    assert {"Парасолька", "Тепла куртка", "Паспорт / ID-картка"} <= items


def test_checklist_hot_and_sunny():
    items = {i.item for i in build_checklist([day(temp_min=20, temp_max=31, uv_index_max=8)])}
    assert {"Легкий одяг", "Сонцезахисні окуляри", "Сонцезахисний крем SPF 50"} <= items
    assert "Парасолька" not in items


def test_message_contains_city_and_items():
    days = [day()]
    text = format_plan_message(CITY, days, build_checklist(days))
    assert "Кропивницький" in text and "Що взяти" in text
