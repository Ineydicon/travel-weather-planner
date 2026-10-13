"""Точка входу: створення FastAPI-застосунку."""
from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles

from app.api import routes, telegram

app = FastAPI(
    title="Travel Weather Planner API",
    version="0.1.0",
    description="Прогноз погоди для поїздки та автоматичний чек-ліст речей. "
    "Зовнішні сервіси: Open-Meteo (погода) і Telegram Bot API (доставка).",
)

app.include_router(routes.router)
app.include_router(telegram.router)

# Фронтенд (статичні файли) — останнім, щоб не перекривати /api та /docs
app.mount("/", StaticFiles(directory="static", html=True), name="static")
