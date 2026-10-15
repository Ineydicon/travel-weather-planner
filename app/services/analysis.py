"""Аналітична логіка: валідація даних з API та генерація статусів-попереджень.

Тут система «приймає рішення» на основі погоди — не просто пересилає числа,
а перевіряє їх і формує висновки для користувача.
"""
from dataclasses import dataclass

from app.schemas import DayForecast

# Коди погоди WMO (https://open-meteo.com/en/docs)
RAIN_CODES = {51, 53, 55, 56, 57, 61, 63, 65, 66, 67, 80, 81, 82}
SNOW_CODES = {71, 73, 75, 77, 85, 86}
STORM_CODES = {95, 96, 99}
FOG_CODES = {45, 48}

# Порогові значення (Trigger values)
RAIN_PROBABILITY_TRIGGER = 50     # %
RAIN_SUM_TRIGGER = 1.0            # мм
STRONG_WIND_TRIGGER = 10.0        # м/с
STORM_WIND_TRIGGER = 15.0         # м/с
FROST_TRIGGER = 0.0               # °C
HEAT_TRIGGER = 30.0               # °C
HIGH_UV_TRIGGER = 6.0
EXTREME_UV_TRIGGER = 8.0


class InvalidForecastError(Exception):
    """Дані від API не пройшли перевірку."""


@dataclass(frozen=True)
class Alert:
    level: str   # "info" | "warning" | "danger"
    text: str

    @property
    def is_severe(self) -> bool:
        return self.level == "danger"


def validate_day(d: DayForecast) -> list[str]:
    """Повертає список проблем у даних одного дня (порожній — дані коректні)."""
    problems = []
    if not -90 <= d.temp_min <= 60 or not -90 <= d.temp_max <= 60:
        problems.append("температура поза фізичними межами")
    if d.temp_min > d.temp_max:
        problems.append("мінімальна температура більша за максимальну")
    if not 0 <= d.precipitation_probability <= 100:
        problems.append("ймовірність опадів не в межах 0–100 %")
    if d.precipitation_sum < 0 or d.wind_speed_max < 0 or d.uv_index_max < 0:
        problems.append("від'ємні опади, вітер або UV-індекс")
    return problems


def validate_forecast(days: list[DayForecast]) -> list[DayForecast]:
    """Відкидає дні з некоректними даними. Якщо коректних немає — помилка."""
    if not days:
        raise InvalidForecastError("API не повернув жодного дня прогнозу.")
    valid = [d for d in days if not validate_day(d)]
    if not valid:
        raise InvalidForecastError("Усі дані прогнозу некоректні — результат не сформовано.")
    return valid


def build_alerts(days: list[DayForecast]) -> list[Alert]:
    """Аналізує прогноз і формує статус-повідомлення (найважливіші — першими)."""
    if not days:
        return []

    t_min = min(d.temp_min for d in days)
    t_max = max(d.temp_max for d in days)
    rain_prob = max(d.precipitation_probability for d in days)
    rain_sum = max(d.precipitation_sum for d in days)
    wind = max(d.wind_speed_max for d in days)
    uv = max(d.uv_index_max for d in days)
    codes = {d.weather_code for d in days}

    alerts: list[Alert] = []

    # Небезпечні явища
    if codes & STORM_CODES:
        alerts.append(Alert("danger", "⛈ Очікується гроза! Уникайте відкритої місцевості."))
    if wind >= STORM_WIND_TRIGGER:
        alerts.append(Alert("danger", f"🌪 Штормовий вітер до {wind:.0f} м/с! Будьте обережні."))
    if t_min < FROST_TRIGGER:
        alerts.append(Alert("danger" if t_min <= -10 else "warning",
                            f"🥶 Мороз до {t_min:.0f} °C — одягніться тепло!"))
    if t_max >= HEAT_TRIGGER:
        alerts.append(Alert("danger" if t_max >= 35 else "warning",
                            f"🔥 Спека до {t_max:.0f} °C — пийте більше води!"))

    # Звичайні попередження
    if codes & SNOW_CODES:
        alerts.append(Alert("warning", "❄️ Сніг — взуйте нековзке взуття."))
    if rain_prob >= RAIN_PROBABILITY_TRIGGER or rain_sum >= RAIN_SUM_TRIGGER or codes & RAIN_CODES:
        alerts.append(Alert("warning", "☔ Візьміть парасольку!"))
    if STRONG_WIND_TRIGGER <= wind < STORM_WIND_TRIGGER:
        alerts.append(Alert("warning", f"💨 Сильний вітер до {wind:.0f} м/с."))
    if uv >= EXTREME_UV_TRIGGER:
        alerts.append(Alert("warning", f"😎 Дуже високий UV-індекс ({uv:.0f}) — потрібен крем SPF 50."))
    elif uv >= HIGH_UV_TRIGGER:
        alerts.append(Alert("info", f"🕶 Високий UV-індекс ({uv:.0f}) — візьміть окуляри."))
    if codes & FOG_CODES:
        alerts.append(Alert("info", "🌫 Туман — обмежена видимість на дорогах."))

    if not alerts:
        alerts.append(Alert("info", "✅ Погода сприятлива — гарного дня!"))

    order = {"danger": 0, "warning": 1, "info": 2}
    return sorted(alerts, key=lambda a: order[a.level])


def has_severe(alerts: list[Alert]) -> bool:
    return any(a.is_severe for a in alerts)
