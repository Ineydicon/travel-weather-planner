"""REST API для вебінтерфейсу."""
from fastapi import APIRouter, HTTPException, Query

from app.schemas import (City, ErrorResponse, HealthResponse, PlanRequest, PlanResponse,
                         SendRequest, SendResponse)

router = APIRouter(prefix="/api/v1")

NOT_READY = HTTPException(status_code=501, detail="Буде реалізовано на наступних етапах")


@router.get("/health", response_model=HealthResponse, tags=["Сервіс"],
            summary="Перевірка стану сервісу")
async def health():
    return HealthResponse(version="0.1.0")


@router.get("/cities", response_model=list[City], tags=["Погода"],
            summary="Пошук міста за назвою (Open-Meteo Geocoding)")
async def search_cities(name: str = Query(min_length=2, examples=["Львів"])):
    raise NOT_READY


@router.post("/plan", response_model=PlanResponse, tags=["Поїздки"],
             summary="Прогноз погоди та чек-ліст для поїздки",
             responses={404: {"model": ErrorResponse, "description": "Місто не знайдено"},
                        502: {"model": ErrorResponse, "description": "Open-Meteo недоступний"}})
async def create_plan(body: PlanRequest):
    raise NOT_READY


@router.get("/trips/{trip_id}", response_model=PlanResponse, tags=["Поїздки"],
            summary="Отримати збережену поїздку",
            responses={404: {"model": ErrorResponse, "description": "Поїздку не знайдено"}})
async def get_trip(trip_id: str):
    raise NOT_READY


@router.post("/trips/{trip_id}/send", response_model=SendResponse, tags=["Поїздки"],
             summary="Надіслати чек-ліст у Telegram",
             responses={404: {"model": ErrorResponse, "description": "Поїздку не знайдено"},
                        502: {"model": ErrorResponse, "description": "Telegram недоступний"}})
async def send_trip(trip_id: str, body: SendRequest):
    raise NOT_READY
