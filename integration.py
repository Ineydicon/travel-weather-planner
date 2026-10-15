"""Скрипт інтеграції: Open-Meteo (API 1) -> обробка -> Telegram (API 2).

Приклади запуску:
    python integration.py Кропивницький
    python integration.py Львів 2026-10-15 2026-10-17
    python integration.py --find-chat-id
"""
import argparse
import asyncio
import sys
from datetime import date, timedelta

from pydantic import ValidationError

from app.config import settings
from app.schemas import PlanRequest
from app.services.analysis import InvalidForecastError, build_alerts, validate_forecast
from app.services.formatter import format_plan_message
from app.services.notifier import TelegramError, find_chats, send_message
from app.services.packing import build_checklist
from app.services.weather import WeatherServiceError, get_forecast, search_cities


def step(n: int, text: str) -> None:
    print(f"[{n}/4] {text}...", flush=True)


async def run(city_name: str, date_from: date, date_to: date) -> None:
    # 0. Перевірка вхідних даних і налаштувань
    PlanRequest(city=city_name, date_from=date_from, date_to=date_to)
    if not settings.telegram_bot_token:
        raise TelegramError("У файлі .env не задано TELEGRAM_BOT_TOKEN.")
    if not settings.telegram_chat_id:
        raise TelegramError("У файлі .env не задано TELEGRAM_CHAT_ID. "
                            "Запустіть: python integration.py --find-chat-id")

    # 1. API 1: координати міста
    step(1, f"Пошук міста «{city_name}» (Open-Meteo Geocoding)")
    city = (await search_cities(city_name, count=1))[0]
    place = ", ".join(p for p in (city.name, city.region, city.country) if p)
    print(f"      OK: {place} ({city.latitude:.2f}, {city.longitude:.2f})")

    # 2. API 1: прогноз
    step(2, f"Отримання прогнозу на {date_from:%d.%m} – {date_to:%d.%m} (Open-Meteo Forecast)")
    days = await get_forecast(city, date_from, date_to)
    for d in days:
        print(f"      {d.day:%d.%m}: {d.temp_min:+.0f}…{d.temp_max:+.0f} °C, "
              f"опади {d.precipitation_probability} %, вітер {d.wind_speed_max:.0f} м/с")

    # 3. Обробка даних: валідація -> аналіз (статуси) -> чек-ліст
    step(3, "Аналіз даних і формування чек-листа")
    days = validate_forecast(days)
    alerts = build_alerts(days)
    for a in alerts:
        print(f"      [{a.level}] {a.text}")
    checklist = build_checklist(days)
    print(f"      OK: {len(checklist)} речей")
    message = format_plan_message(city, days, checklist, alerts)

    # 4. API 2: надсилання в Telegram
    step(4, "Надсилання в Telegram (Bot API sendMessage)")
    await send_message(settings.telegram_bot_token, settings.telegram_chat_id, message)
    print("      OK: повідомлення доставлено\n")
    print(message)


async def show_chat_ids() -> None:
    if not settings.telegram_bot_token:
        raise TelegramError("У файлі .env не задано TELEGRAM_BOT_TOKEN.")
    chats = await find_chats(settings.telegram_bot_token)
    if not chats:
        print("Повідомлень не знайдено. Відкрийте свого бота в Telegram, "
              "натисніть Start (/start) і запустіть команду ще раз.")
        return
    print("Знайдені чати (впишіть потрібний chat_id у .env як TELEGRAM_CHAT_ID):")
    for chat_id, name in chats:
        print(f"  TELEGRAM_CHAT_ID={chat_id}    ({name})")


def parse_args() -> argparse.Namespace:
    today = date.today()
    p = argparse.ArgumentParser(description="Прогноз погоди + чек-ліст речей -> Telegram")
    p.add_argument("city", nargs="?", default="Кропивницький", help="назва міста")
    p.add_argument("date_from", nargs="?", type=date.fromisoformat, default=today,
                   help="дата початку, РРРР-ММ-ДД (за замовчуванням сьогодні)")
    p.add_argument("date_to", nargs="?", type=date.fromisoformat, default=None,
                   help="дата кінця, РРРР-ММ-ДД (за замовчуванням +2 дні)")
    p.add_argument("--find-chat-id", action="store_true", help="показати chat_id для .env")
    args = p.parse_args()
    if args.date_to is None:
        args.date_to = args.date_from + timedelta(days=2)
    return args


def main() -> int:
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")  # кирилиця та емодзі в консолі Windows
    args = parse_args()
    try:
        if args.find_chat_id:
            asyncio.run(show_chat_ids())
        else:
            asyncio.run(run(args.city, args.date_from, args.date_to))
        return 0
    except ValidationError as e:
        print("ПОМИЛКА у вхідних даних: " + "; ".join(
            err["msg"].removeprefix("Value error, ") for err in e.errors()))
    except WeatherServiceError as e:
        print(f"ПОМИЛКА Open-Meteo: {e}")
    except InvalidForecastError as e:
        print(f"ПОМИЛКА даних: {e}")
    except TelegramError as e:
        print(f"ПОМИЛКА Telegram: {e}")
    except KeyboardInterrupt:
        print("Перервано користувачем.")
    return 1


if __name__ == "__main__":
    sys.exit(main())
