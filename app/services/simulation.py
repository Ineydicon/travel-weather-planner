"""Симуляція різних відповідей API для демонстрації логіки (без реальних запитів)."""
from datetime import date, timedelta

from app.schemas import City, DayForecast

DEMO_CITY = City(name="Демо-місто", country="Симуляція", latitude=0, longitude=0,
                 timezone="Europe/Kyiv")

# Назва сценарію -> параметри "відповіді API"
SCENARIOS: dict[str, dict] = {
    "rain":  dict(title="☔ Злива", temp_min=8, temp_max=13, precipitation_sum=12.5,
                  precipitation_probability=95, wind_speed_max=7, uv_index_max=1, weather_code=65),
    "heat":  dict(title="🔥 Спека", temp_min=22, temp_max=36, precipitation_sum=0,
                  precipitation_probability=0, wind_speed_max=3, uv_index_max=9, weather_code=0),
    "frost": dict(title="🥶 Мороз", temp_min=-14, temp_max=-6, precipitation_sum=2,
                  precipitation_probability=60, wind_speed_max=6, uv_index_max=1, weather_code=73),
    "storm": dict(title="⛈ Гроза", temp_min=17, temp_max=25, precipitation_sum=20,
                  precipitation_probability=90, wind_speed_max=18, uv_index_max=4, weather_code=95),
    "clear": dict(title="☀️ Ясно", temp_min=14, temp_max=22, precipitation_sum=0,
                  precipitation_probability=5, wind_speed_max=3, uv_index_max=4, weather_code=0),
}


def scenario_forecast(name: str, days: int = 1, start: date | None = None) -> list[DayForecast]:
    params = {k: v for k, v in SCENARIOS[name].items() if k != "title"}
    start = start or date.today()
    return [DayForecast(day=start + timedelta(days=i), **params) for i in range(days)]
