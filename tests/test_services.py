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
    assert days[1].precipitation_probability == 0
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


def test_telegram_send_ok():
    def handler(request):
        assert request.url.path.endswith("/sendMessage")
        return httpx.Response(200, json={"ok": True, "result": {"message_id": 1}})
    asyncio.run(send_message("TOKEN", 123, "hello", client=mock_client(handler)))


def test_telegram_bad_token():
    handler = lambda request: httpx.Response(401, json={"ok": False, "description": "Unauthorized"})
    with pytest.raises(TelegramError, match="токен") as e:
        asyncio.run(send_message("SECRET123", 123, "hi", client=mock_client(handler)))
    assert "SECRET123" not in str(e.value)


def test_telegram_chat_not_found():
    handler = lambda request: httpx.Response(
        400, json={"ok": False, "description": "Bad Request: chat not found"})
    with pytest.raises(TelegramError, match="/start"):
        asyncio.run(send_message("T", 1, "hi", client=mock_client(handler)))


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


def test_russian_city_name_is_normalized():
    def handler(request):
        assert request.url.params["name"] == "Київ"
        return httpx.Response(200, json={"results": [{
            "name": "Київ", "country": "Україна", "latitude": 50.45, "longitude": 30.52,
            "timezone": "Europe/Kyiv", "population": 2797553}]})
    city = asyncio.run(search_cities("Киев", count=1, client=mock_client(handler)))[0]
    assert city.country == "Україна"


def test_biggest_city_is_chosen():
    handler = lambda request: httpx.Response(200, json={"results": [
        {"name": "Odessa", "country": "США", "latitude": 31.8, "longitude": -102.3,
         "timezone": "America/Chicago", "population": 99940},
        {"name": "Одеса", "country": "Україна", "latitude": 46.48, "longitude": 30.72,
         "timezone": "Europe/Kyiv", "population": 1015826}]})
    city = asyncio.run(search_cities("Odessa", count=1, client=mock_client(handler)))[0]
    assert city.country == "Україна"


def test_transliteration_fallback_for_small_places():
    seen = []

    def handler(request):
        seen.append(request.url.params["name"])
        if request.url.params["name"] == "Velyka Vyska":
            return httpx.Response(200, json={"results": [{
                "name": "Велика Виска", "country": "Україна", "latitude": 48.5,
                "longitude": 31.9, "timezone": "Europe/Kyiv"}]})
        return httpx.Response(200, json={})
    city = asyncio.run(search_cities("Велика Виска", count=1, client=mock_client(handler)))[0]
    assert seen == ["Велика Виска", "Velyka Vyska"] and city.name == "Велика Виска"


def test_query_cleanup():
    from app.services.weather import normalize_city, transliterate
    assert normalize_city("м. Буча") == "Буча"
    assert normalize_city("Львів, Україна") == "Львів"
    assert normalize_city("Слов’янськ") == "Слов'янськ"
    assert transliterate("Слов'янськ") == "Sloviansk"
    assert transliterate("Згурівка") == "Zghurivka"


def test_openstreetmap_fallback_for_foreign_names():
    def handler(request):
        if request.url.host == "nominatim.openstreetmap.org":
            assert request.headers["User-Agent"].startswith("TravelWeatherPlanner")
            return httpx.Response(200, json=[{
                "name": "Лісабон", "lat": "38.7077", "lon": "-9.1365",
                "address": {"country": "Португалія", "state": "Лісабон"}}])
        return httpx.Response(200, json={})
    city = asyncio.run(search_cities("Лісабон", count=1, client=mock_client(handler)))[0]
    assert city.country == "Португалія" and round(city.longitude, 1) == -9.1


def test_rate_limited_geocoding_falls_back_to_openstreetmap():
    def handler(request):
        if request.url.host == "nominatim.openstreetmap.org":
            return httpx.Response(200, json=[{"name": "Львів", "lat": "49.84", "lon": "24.03",
                                              "address": {"country": "Україна"}}])
        return httpx.Response(429, json={"reason": "Too many requests"})
    city = asyncio.run(search_cities("Львів", count=1, client=mock_client(handler)))[0]
    assert city.name == "Львів"


def test_rate_limited_forecast_falls_back_to_met_norway():
    def handler(request):
        if request.url.host == "api.met.no":
            return httpx.Response(200, json={"properties": {"timeseries": [{
                "time": "2026-10-15T09:00:00Z",
                "data": {"instant": {"details": {"air_temperature": 11.0, "wind_speed": 4.0,
                                                 "ultraviolet_index_clear_sky": 2.0}},
                         "next_1_hours": {"summary": {"symbol_code": "lightrain"},
                                          "details": {"precipitation_amount": 1.2,
                                                      "probability_of_precipitation": 70}}}}]}})
        return httpx.Response(429, json={"reason": "Too many requests"})
    days = asyncio.run(get_forecast(CITY, date(2026, 10, 15), date(2026, 10, 15),
                                    client=mock_client(handler)))
    assert days[0].weather_code == 61 and days[0].precipitation_probability == 70
