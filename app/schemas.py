"""Схеми даних API (Pydantic). На їх основі FastAPI будує OpenAPI-специфікацію."""
from datetime import date, timedelta
from typing import Literal

from pydantic import BaseModel, Field, model_validator

FORECAST_DAYS_LIMIT = 16  # Open-Meteo дає прогноз максимум на 16 днів


class HealthResponse(BaseModel):
    status: Literal["ok"] = "ok"
    version: str = Field(examples=["0.1.0"])


class City(BaseModel):
    name: str = Field(examples=["Львів"])
    country: str = Field(examples=["Україна"])
    region: str | None = Field(default=None, examples=["Львівська область"])
    latitude: float = Field(examples=[49.8383])
    longitude: float = Field(examples=[24.0232])
    timezone: str = Field(examples=["Europe/Kyiv"])


class PlanRequest(BaseModel):
    city: str = Field(min_length=2, max_length=100, examples=["Львів"])
    date_from: date = Field(examples=["2026-10-20"])
    date_to: date = Field(examples=["2026-10-23"])

    @model_validator(mode="after")
    def check_dates(self):
        today = date.today()
        if self.date_to < self.date_from:
            raise ValueError("date_to не може бути раніше за date_from")
        if self.date_from < today:
            raise ValueError("Дата початку поїздки вже минула")
        if self.date_to > today + timedelta(days=FORECAST_DAYS_LIMIT - 1):
            raise ValueError(f"Прогноз доступний лише на {FORECAST_DAYS_LIMIT} днів уперед")
        return self


class DayForecast(BaseModel):
    day: date
    temp_min: float = Field(description="°C", examples=[6.2])
    temp_max: float = Field(description="°C", examples=[14.8])
    precipitation_sum: float = Field(description="мм", examples=[3.4])
    precipitation_probability: int = Field(description="%", examples=[70])
    wind_speed_max: float = Field(description="м/с", examples=[8.1])
    uv_index_max: float = Field(examples=[2.5])
    weather_code: int = Field(description="Код погоди WMO", examples=[61])


class ChecklistItem(BaseModel):
    category: Literal["Одяг", "Аксесуари", "Здоров'я", "Документи"]
    item: str = Field(examples=["Парасолька"])
    reason: str = Field(examples=["Ймовірність дощу 70 %"])


class PlanResponse(BaseModel):
    trip_id: str = Field(examples=["3f9c2a1e-7b4d-4c8e-9a51-2d6f0b8e1c33"])
    city: City
    days: list[DayForecast]
    checklist: list[ChecklistItem]


class SendRequest(BaseModel):
    chat_id: int = Field(description="Telegram chat_id (бот повідомляє його у відповідь на /start)",
                         examples=[123456789])


class SendResponse(BaseModel):
    sent: bool = True


class ErrorResponse(BaseModel):
    detail: str = Field(examples=["Місто не знайдено"])
