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
