from datetime import date, timedelta

from fastapi.testclient import TestClient

from app.main import app

client = TestClient(app)


def test_health():
    r = client.get("/api/v1/health")
    assert r.status_code == 200
    assert r.json()["status"] == "ok"


def test_openapi_available():
    r = client.get("/openapi.json")
    assert r.status_code == 200
    assert "/api/v1/plan" in r.json()["paths"]


def test_plan_rejects_wrong_dates():
    today = date.today()
    r = client.post("/api/v1/plan", json={
        "city": "Львів",
        "date_from": str(today + timedelta(days=3)),
        "date_to": str(today + timedelta(days=1)),
    })
    assert r.status_code == 422


def test_plan_rejects_too_far_dates():
    today = date.today()
    r = client.post("/api/v1/plan", json={
        "city": "Львів",
        "date_from": str(today + timedelta(days=20)),
        "date_to": str(today + timedelta(days=22)),
    })
    assert r.status_code == 422


def test_webhook_requires_secret():
    r = client.post("/telegram/webhook", json={})
    assert r.status_code == 403


def test_tick_requires_secret():
    r = client.post("/api/v1/tick")
    assert r.status_code == 403


def test_tick_runs_scheduler():
    from app.config import settings

    class FakeStorage:
        def all(self):
            return [1, 2]

    class FakeBot:
        storage = FakeStorage()
        ticks = 0

        async def tick(self, now):
            FakeBot.ticks += 1

    old_secret, settings.cron_secret = settings.cron_secret, "test-secret"
    app.state.bot = FakeBot()
    try:
        r = client.post("/api/v1/tick", headers={"X-Cron-Secret": "test-secret"})
        assert r.status_code == 200 and r.json()["subscriptions"] == 2 and FakeBot.ticks == 1
        assert client.post("/api/v1/tick", headers={"X-Cron-Secret": "wrong"}).status_code == 403
    finally:
        settings.cron_secret = old_secret


def test_plan_ok_with_fake_weather():
    from app.schemas import City, DayForecast
    from app.services import weather

    async def fake_search(name, count=1):
        return [City(name="Львів", country="Україна", latitude=49.8, longitude=24.0,
                     timezone="Europe/Kyiv")]

    async def fake_forecast(city, d1, d2):
        return [DayForecast(day=d1, temp_min=4, temp_max=11, precipitation_sum=5,
                            precipitation_probability=90, wind_speed_max=5, uv_index_max=1,
                            weather_code=63)]

    saved = weather.search_cities, weather.get_forecast
    weather.search_cities, weather.get_forecast = fake_search, fake_forecast
    try:
        today = date.today()
        r = client.post("/api/v1/plan", json={"city": "Львів", "date_from": str(today),
                                               "date_to": str(today)})
    finally:
        weather.search_cities, weather.get_forecast = saved
    assert r.status_code == 200
    data = r.json()
    assert data["city"]["name"] == "Львів"
    assert any("парасольку" in a["text"] for a in data["alerts"])
    assert any(i["item"] == "Парасолька" for i in data["checklist"])


def test_index_page():
    r = client.get("/")
    assert r.status_code == 200 and "Travel Weather Planner" in r.text
