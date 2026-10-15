import asyncio
from datetime import date, datetime, timedelta, timezone

import pytest

from app.bot import keyboards as kb
from app.bot.logic import WeatherBot, parse_date
from app.schemas import City, DayForecast
from app.services.weather import CityNotFoundError
from app.storage import SubscriptionStorage

KYIV = City(name="Київ", country="Україна", latitude=50.45, longitude=30.52,
            timezone="Europe/Kyiv")


class FakeApi:
    def __init__(self):
        self.sent: list[tuple[int, str, dict | None]] = []

    async def send(self, chat_id, text, markup=None):
        self.sent.append((chat_id, text, markup))

    async def answer(self, callback_id, text=""):
        pass

    @property
    def last(self) -> str:
        return self.sent[-1][1]


async def fake_search(name, count=1):
    if name.lower().startswith("qwe"):
        raise CityNotFoundError(f"Місто «{name}» не знайдено. Перевірте назву.")
    return [KYIV.model_copy(update={"name": name})]


def make_forecast(**kw):
    async def fake_forecast(city, d1, d2):
        n = (d2 - d1).days + 1
        base = dict(temp_min=5, temp_max=12, precipitation_sum=3, precipitation_probability=80,
                    wind_speed_max=4, uv_index_max=2, weather_code=61)
        base.update(kw)
        return [DayForecast(day=d1 + timedelta(days=i), **base) for i in range(n)]
    return fake_forecast


@pytest.fixture
def setup():
    api = FakeApi()
    storage = SubscriptionStorage(":memory:")
    bot = WeatherBot(api, storage, search_cities=fake_search, get_forecast=make_forecast())
    return bot, api, storage


def msg(text, chat_id=1):
    return {"update_id": 1, "message": {"chat": {"id": chat_id}, "text": text}}


def press(data, chat_id=1):
    return {"update_id": 1, "callback_query": {"id": "cb", "data": data,
                                               "message": {"chat": {"id": chat_id}}}}


def run(coro):
    return asyncio.run(coro)


def test_start_shows_menu(setup):
    bot, api, _ = setup
    run(bot.handle_update(msg("/start")))
    assert "Привіт" in api.last and api.sent[-1][2] == kb.MAIN_MENU


def test_help(setup):
    bot, api, _ = setup
    run(bot.handle_update(msg("/help")))
    assert "/subscribe" in api.last


def test_city_text_gives_today_weather(setup):
    bot, api, _ = setup
    run(bot.handle_update(msg("Київ")))
    assert "Погода на сьогодні" in api.last and "Візьміть парасольку!" in api.last


def test_unknown_city_error(setup):
    bot, api, _ = setup
    run(bot.handle_update(msg("Qwertyzxc")))
    assert api.last.startswith("❌") and "не знайдено" in api.last


def test_trip_flow_with_buttons(setup):
    bot, api, _ = setup
    run(bot.handle_update(msg(kb.BTN_TRIP)))
    run(bot.handle_update(msg("Львів")))
    assert "inline_keyboard" in api.sent[-1][2]
    run(bot.handle_update(press("trip:3")))
    assert "Поїздка: Львів" in api.last and api.last.count("• ") == 3


def test_plan_command_with_dates(setup):
    bot, api, _ = setup
    d1 = date.today() + timedelta(days=1)
    d2 = d1 + timedelta(days=1)
    run(bot.handle_update(msg(f"/plan Івано-Франківськ {d1:%d.%m} {d2:%d.%m}")))
    assert "Івано-Франківськ" in api.last and "Що взяти" in api.last


def test_plan_rejects_far_dates(setup):
    bot, api, _ = setup
    far = date.today() + timedelta(days=40)
    run(bot.handle_update(msg(f"/plan Львів {far.isoformat()}")))
    assert api.last.startswith("❌") and "16 днів" in api.last


def test_subscribe_and_unsubscribe(setup):
    bot, api, storage = setup
    run(bot.handle_update(msg("/subscribe Київ 7")))
    assert storage.get(1).hour == 7 and "07:00" in api.last
    run(bot.handle_update(msg("/unsubscribe")))
    assert storage.get(1) is None and "вимкнено" in api.last


def test_subscribe_via_buttons(setup):
    bot, api, storage = setup
    run(bot.handle_update(msg(kb.BTN_SUB)))
    run(bot.handle_update(msg("Одеса")))
    run(bot.handle_update(press("hour:8")))
    sub = storage.get(1)
    assert sub.city.name == "Одеса" and sub.hour == 8


def test_simulation_storm_sends_warning(setup):
    bot, api, _ = setup
    run(bot.handle_update(press("sim:storm")))
    assert "СИМУЛЯЦІЯ" in api.sent[-2][1]
    assert "ПОПЕРЕДЖЕННЯ" in api.last


def test_scheduler_sends_morning_once(setup):
    bot, api, storage = setup
    storage.upsert(1, KYIV, hour=7)
    seven = datetime(2026, 10, 15, 4, 5, tzinfo=timezone.utc)
    run(bot.tick(seven))
    run(bot.tick(seven + timedelta(minutes=10)))
    morning = [t for _, t, _ in api.sent if "Доброго ранку" in t]
    assert len(morning) == 1


def test_scheduler_not_at_other_hour(setup):
    bot, api, storage = setup
    storage.upsert(1, KYIV, hour=7)
    run(bot.tick(datetime(2026, 10, 15, 2, 0, tzinfo=timezone.utc)))
    assert not any("Доброго ранку" in t for _, t, _ in api.sent)


def test_scheduler_storm_warning_once():
    api = FakeApi()
    storage = SubscriptionStorage(":memory:")
    bot = WeatherBot(api, storage, search_cities=fake_search,
                     get_forecast=make_forecast(weather_code=95), watch_interval=timedelta(0))
    storage.upsert(1, KYIV, hour=7)
    noon = datetime(2026, 10, 15, 9, 0, tzinfo=timezone.utc)
    run(bot.tick(noon))
    run(bot.tick(noon + timedelta(hours=1)))
    warnings = [t for _, t, _ in api.sent if "ПОПЕРЕДЖЕННЯ" in t]
    assert len(warnings) == 1


def test_parse_date():
    today = date(2026, 10, 15)
    assert parse_date("20.10", today) == date(2026, 10, 20)
    assert parse_date("2026-10-21", today) == date(2026, 10, 21)
    assert parse_date("01.01", today) == date(2027, 1, 1)


def test_storage_sqlite_roundtrip(tmp_path=None):
    import os, tempfile
    path = os.path.join(tempfile.mkdtemp(), "sub.db")
    s1 = SubscriptionStorage(f"sqlite:///{path}")
    s1.upsert(42, KYIV, 7)
    s1.mark_sent(42, date(2026, 10, 15))
    s2 = SubscriptionStorage(f"sqlite:///{path}")
    sub = s2.get(42)
    assert sub.city.name == "Київ" and sub.hour == 7 and sub.last_sent == date(2026, 10, 15)
    assert s2.delete(42) and s2.get(42) is None


def test_greeting_depends_on_hour():
    from app.bot.logic import greeting
    assert "ранку" in greeting(7) and "день" in greeting(13)
    assert "вечір" in greeting(18) and "ночі" in greeting(2)
