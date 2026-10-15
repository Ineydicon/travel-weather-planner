from datetime import date

import pytest

from app.schemas import DayForecast
from app.services.analysis import (InvalidForecastError, build_alerts, has_severe,
                                   validate_day, validate_forecast)
from app.services.simulation import scenario_forecast


def day(**kw) -> DayForecast:
    base = dict(day=date(2026, 10, 15), temp_min=12, temp_max=18, precipitation_sum=0,
                precipitation_probability=0, wind_speed_max=3, uv_index_max=2, weather_code=0)
    base.update(kw)
    return DayForecast(**base)


def texts(days) -> str:
    return " ".join(a.text for a in build_alerts(days))


def test_rain_gives_umbrella_status():
    assert "Візьміть парасольку!" in texts([day(precipitation_probability=80)])


def test_rain_detected_by_weather_code():
    assert "парасольку" in texts([day(weather_code=63)])


def test_storm_is_severe():
    alerts = build_alerts([day(weather_code=95)])
    assert has_severe(alerts) and "гроза" in alerts[0].text.lower()


def test_strong_vs_storm_wind():
    assert "Сильний вітер" in texts([day(wind_speed_max=12)])
    assert "Штормовий вітер" in texts([day(wind_speed_max=18)])


def test_frost_and_heat():
    assert "Мороз" in texts([day(temp_min=-5, temp_max=1)])
    assert "Спека" in texts([day(temp_min=20, temp_max=33)])


def test_good_weather_status():
    alerts = build_alerts([day()])
    assert len(alerts) == 1 and "сприятлива" in alerts[0].text
    assert not has_severe(alerts)


def test_dangerous_alerts_come_first():
    alerts = build_alerts([day(precipitation_probability=90, weather_code=95)])
    assert alerts[0].level == "danger"


def test_validate_detects_bad_values():
    assert validate_day(day(temp_min=20, temp_max=10))
    assert validate_day(day(precipitation_probability=150))
    assert validate_day(day(wind_speed_max=-1))
    assert not validate_day(day())


def test_validate_drops_invalid_days():
    good, bad = day(), day(temp_min=100, temp_max=120)
    assert validate_forecast([good, bad]) == [good]


def test_validate_rejects_all_invalid():
    with pytest.raises(InvalidForecastError):
        validate_forecast([day(precipitation_probability=-5)])
    with pytest.raises(InvalidForecastError):
        validate_forecast([])


@pytest.mark.parametrize("name,expected", [
    ("rain", "парасольку"), ("heat", "Спека"), ("frost", "Мороз"),
    ("storm", "гроза"), ("clear", "сприятлива"),
])
def test_simulation_scenarios(name, expected):
    days = validate_forecast(scenario_forecast(name))
    assert expected.lower() in texts(days).lower()
