from datetime import datetime, timezone

from fastapi import APIRouter, Header, HTTPException, Query, Request

from app.config import settings
from app.schemas import (AlertOut, City, ErrorResponse, HealthResponse, PlanRequest,
                         PlanResponse, TickResponse)
from app.services import weather
from app.services.analysis import InvalidForecastError, build_alerts, validate_forecast
from app.services.packing import build_checklist

router = APIRouter(prefix="/api/v1")

VERSION = "1.0.0"
WEATHER_ERRORS = {404: {"model": ErrorResponse, "description": "Місто не знайдено"},
                  502: {"model": ErrorResponse, "description": "Open-Meteo недоступний"}}


@router.get("/health", response_model=HealthResponse, tags=["Сервіс"],
            summary="Перевірка стану сервісу")
async def health():
    return HealthResponse(version=VERSION)


@router.get("/cities", response_model=list[City], tags=["Погода"], responses=WEATHER_ERRORS,
            summary="Пошук міста за назвою (Open-Meteo Geocoding)")
async def search_cities(name: str = Query(min_length=2, max_length=100, examples=["Львів"])):
    try:
        return await weather.search_cities(name, count=5)
    except weather.CityNotFoundError as e:
        raise HTTPException(404, str(e))
    except weather.WeatherServiceError as e:
        raise HTTPException(502, str(e))


@router.post("/plan", response_model=PlanResponse, tags=["Погода"], responses=WEATHER_ERRORS,
             summary="Прогноз, статуси-попередження та чек-ліст для поїздки")
async def create_plan(body: PlanRequest):
    try:
        city = (await weather.search_cities(body.city, count=1))[0]
        days = validate_forecast(await weather.get_forecast(city, body.date_from, body.date_to))
    except weather.CityNotFoundError as e:
        raise HTTPException(404, str(e))
    except (weather.WeatherServiceError, InvalidForecastError) as e:
        raise HTTPException(502, str(e))
    return PlanResponse(
        city=city, days=days,
        alerts=[AlertOut(level=a.level, text=a.text) for a in build_alerts(days)],
        checklist=build_checklist(days))


@router.post("/tick", response_model=TickResponse, tags=["Сервіс"],
             summary="Планувальник: ранкова розсилка й перевірка небезпечної погоди",
             description="Викликається за розкладом (GitHub Actions). "
                         "Потрібен заголовок X-Cron-Secret.")
async def tick(request: Request, x_cron_secret: str | None = Header(default=None)):
    if not settings.cron_secret or x_cron_secret != settings.cron_secret:
        raise HTTPException(403, "Невірний секрет планувальника")
    bot = request.app.state.bot
    await bot.tick(datetime.now(timezone.utc))
    return TickResponse(subscriptions=len(bot.storage.all()))
