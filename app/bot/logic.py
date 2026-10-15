"""Логіка Telegram-бота: команди, кнопки, підписки та планувальник розсилки."""
import logging
import re
from datetime import date, datetime, timedelta
from typing import Awaitable, Callable, Protocol
from zoneinfo import ZoneInfo

from pydantic import ValidationError

from app.bot import keyboards as kb
from app.schemas import City, DayForecast, PlanRequest
from app.services import weather
from app.services.analysis import InvalidForecastError, build_alerts, has_severe, validate_forecast
from app.services.formatter import format_alert_message, format_plan_message, format_today_message
from app.services.packing import build_checklist
from app.services.simulation import DEMO_CITY, SCENARIOS, scenario_forecast
from app.storage import Subscription, SubscriptionStorage

log = logging.getLogger("bot")

HELP_TEXT = (
    "Я — Travel Weather Planner 🧳\n"
    "Аналізую прогноз погоди й підказую, що взяти з собою.\n\n"
    "Команди:\n"
    "/weather Місто — погода на сьогодні\n"
    "/plan Місто [дата] [дата] — поїздка, напр. /plan Львів 20.10 22.10\n"
    "/subscribe Місто [година] — щоденна розсилка, напр. /subscribe Київ 7\n"
    "/me — моя підписка\n"
    "/unsubscribe — вимкнути розсилку\n"
    "/simulate — демонстрація логіки на тестових даних\n"
    "/help — ця довідка\n\n"
    "Або просто напишіть назву міста 🙂"
)

COMMANDS = [
    ("start", "Почати"), ("weather", "Погода на сьогодні"), ("plan", "Спланувати поїздку"),
    ("subscribe", "Щоденна розсилка"), ("me", "Моя підписка"),
    ("unsubscribe", "Вимкнути розсилку"), ("simulate", "Симуляція"), ("help", "Довідка"),
]


class BotApi(Protocol):
    async def send(self, chat_id: int, text: str, markup: dict | None = None) -> None: ...
    async def answer(self, callback_id: str, text: str = "") -> None: ...


class UserError(Exception):
    """Помилка, яку треба просто показати користувачу."""


def parse_date(text: str, today: date) -> date:
    """Приймає 2026-10-20, 20.10.2026 або 20.10 (поточний/наступний рік)."""
    text = text.strip()
    try:
        if re.fullmatch(r"\d{4}-\d{2}-\d{2}", text):
            return date.fromisoformat(text)
        if m := re.fullmatch(r"(\d{1,2})\.(\d{1,2})(?:\.(\d{4}))?", text):
            d, mth, y = int(m[1]), int(m[2]), int(m[3]) if m[3] else today.year
            result = date(y, mth, d)
            if not m[3] and result < today:
                result = date(y + 1, mth, d)
            return result
    except ValueError:
        pass
    raise UserError(f"Не розумію дату «{text}». Приклад: 20.10 або 2026-10-20")


class WeatherBot:
    def __init__(self, api: BotApi, storage: SubscriptionStorage, tz: str = "Europe/Kyiv",
                 search_cities: Callable[..., Awaitable[list[City]]] = weather.search_cities,
                 get_forecast: Callable[..., Awaitable[list[DayForecast]]] = weather.get_forecast,
                 watch_interval: timedelta = timedelta(hours=1)):
        self.api = api
        self.storage = storage
        self.tz = ZoneInfo(tz)
        self.search_cities = search_cities
        self.get_forecast = get_forecast
        self.watch_interval = watch_interval
        self.state: dict[int, dict] = {}       # що бот очікує від користувача
        self._last_watch: datetime | None = None

    def today(self) -> date:
        return datetime.now(self.tz).date()

    # ------------------------------------------------------------------ вхідні оновлення
    async def handle_update(self, update: dict) -> None:
        if cb := update.get("callback_query"):
            await self._handle_callback(cb)
        elif (msg := update.get("message")) and "text" in msg:
            await self._handle_text(msg["chat"]["id"], msg["text"].strip())

    async def _handle_text(self, chat_id: int, text: str) -> None:
        log.info("chat %s: %s", chat_id, text)
        try:
            if text.startswith("/"):
                cmd, _, args = text.partition(" ")
                await self._command(chat_id, cmd.split("@")[0].lower(), args.strip())
            elif text == kb.BTN_TODAY:
                await self._ask_or_today(chat_id)
            elif text == kb.BTN_TRIP:
                self.state[chat_id] = {"step": "trip_city"}
                await self.api.send(chat_id, "🧳 Куди їдете? Напишіть назву міста.")
            elif text == kb.BTN_SUB:
                await self._subscription_menu(chat_id)
            elif text == kb.BTN_SIM:
                await self._simulation_menu(chat_id)
            elif text == kb.BTN_HELP:
                await self.api.send(chat_id, HELP_TEXT, kb.MAIN_MENU)
            else:
                await self._free_text(chat_id, text)
        except UserError as e:
            await self.api.send(chat_id, f"❌ {e}")
        except (weather.WeatherServiceError, InvalidForecastError) as e:
            await self.api.send(chat_id, f"❌ {e}")

    async def _command(self, chat_id: int, cmd: str, args: str) -> None:
        if cmd == "/start":
            self.state.pop(chat_id, None)
            await self.api.send(
                chat_id,
                "👋 Привіт! Я допоможу зібрати речі в дорогу й щоранку підкажу, "
                "що взяти з собою.\n\nОберіть дію в меню нижче 👇\n"
                f"Ваш chat_id: {chat_id}",
                kb.MAIN_MENU)
        elif cmd == "/help":
            await self.api.send(chat_id, HELP_TEXT, kb.MAIN_MENU)
        elif cmd == "/weather":
            if args:
                await self._send_today(chat_id, await self._find_city(args))
            else:
                await self._ask_or_today(chat_id)
        elif cmd == "/plan":
            await self._plan_command(chat_id, args)
        elif cmd == "/subscribe":
            await self._subscribe_command(chat_id, args)
        elif cmd == "/unsubscribe":
            await self._unsubscribe(chat_id)
        elif cmd == "/me":
            await self._subscription_menu(chat_id)
        elif cmd == "/simulate":
            await self._simulation_menu(chat_id)
        else:
            await self.api.send(chat_id, "Невідома команда. Спробуйте /help")

    async def _free_text(self, chat_id: int, text: str) -> None:
        """Текст без команди: відповідь на запитання бота або назва міста."""
        step = self.state.get(chat_id, {}).get("step")
        city = await self._find_city(text)
        if step == "trip_city":
            self.state[chat_id] = {"step": "trip_days", "city": city}
            await self.api.send(chat_id, f"📍 {city.name}, {city.country}. На скільки днів?",
                                kb.trip_days_kb())
        elif step == "sub_city":
            self.state[chat_id] = {"step": "sub_hour", "city": city}
            await self.api.send(chat_id, f"📍 {city.name}. О котрій надсилати прогноз?",
                                kb.hours_kb())
        else:
            self.state.pop(chat_id, None)
            await self._send_today(chat_id, city)

    # ------------------------------------------------------------------ inline-кнопки
    async def _handle_callback(self, cb: dict) -> None:
        chat_id = cb["message"]["chat"]["id"]
        action, _, value = cb.get("data", "").partition(":")
        await self.api.answer(cb["id"])
        log.info("chat %s: [кнопка] %s:%s", chat_id, action, value)
        state = self.state.get(chat_id, {})
        try:
            if action == "trip" and state.get("city"):
                start = self.today()
                await self._send_plan(chat_id, state["city"], start,
                                      start + timedelta(days=int(value) - 1))
                self.state.pop(chat_id, None)
            elif action == "hour" and state.get("city"):
                await self._save_subscription(chat_id, state["city"], int(value))
            elif action == "sub":
                await self._subscription_action(chat_id, value)
            elif action == "sim" and value in SCENARIOS:
                await self._send_simulation(chat_id, value)
            else:
                await self.api.send(chat_id, "Ця кнопка застаріла. Почніть знову: /start")
        except (weather.WeatherServiceError, InvalidForecastError, UserError) as e:
            await self.api.send(chat_id, f"❌ {e}")

    # ------------------------------------------------------------------ сценарії
    async def _find_city(self, name: str) -> City:
        if len(name) < 2 or len(name) > 100:
            raise UserError("Назва міста має бути від 2 до 100 символів.")
        return (await self.search_cities(name, count=1))[0]

    async def _forecast(self, city: City, d1: date, d2: date) -> list[DayForecast]:
        return validate_forecast(await self.get_forecast(city, d1, d2))

    async def _ask_or_today(self, chat_id: int) -> None:
        if sub := self.storage.get(chat_id):
            await self._send_today(chat_id, sub.city)
        else:
            self.state[chat_id] = {"step": "today_city"}
            await self.api.send(chat_id, "🏙 Напишіть назву міста.")

    async def _send_today(self, chat_id: int, city: City, greeting: str = "🌤 Погода на сьогодні"):
        today = self.today()
        days = await self._forecast(city, today, today)
        alerts = build_alerts(days)
        text = format_today_message(city, days[0], build_checklist(days), alerts, greeting)
        await self.api.send(chat_id, text, kb.MAIN_MENU)
        return alerts

    async def _plan_command(self, chat_id: int, args: str) -> None:
        if not args:
            self.state[chat_id] = {"step": "trip_city"}
            await self.api.send(chat_id, "🧳 Куди їдете? Напишіть назву міста.")
            return
        # Місто може складатися з кількох слів: «Івано-Франківськ», «Кам'янець-Подільський», «Нью Йорк»
        parts = args.split()
        dates = []
        while parts and re.fullmatch(r"[\d.\-]+", parts[-1]) and len(dates) < 2:
            dates.insert(0, parts.pop())
        city = await self._find_city(" ".join(parts))
        if not dates:
            self.state[chat_id] = {"step": "trip_days", "city": city}
            await self.api.send(chat_id, f"📍 {city.name}. На скільки днів?", kb.trip_days_kb())
            return
        today = self.today()
        d1 = parse_date(dates[0], today)
        d2 = parse_date(dates[1], today) if len(dates) > 1 else d1
        await self._send_plan(chat_id, city, d1, d2)

    async def _send_plan(self, chat_id: int, city: City, d1: date, d2: date) -> None:
        try:
            PlanRequest(city=city.name, date_from=d1, date_to=d2)   # валідація дат
        except ValidationError as e:
            raise UserError("; ".join(err["msg"].removeprefix("Value error, ")
                                      for err in e.errors()))
        days = await self._forecast(city, d1, d2)
        text = format_plan_message(city, days, build_checklist(days), build_alerts(days))
        await self.api.send(chat_id, text, kb.MAIN_MENU)

    # ------------------------------------------------------------------ підписка
    async def _subscribe_command(self, chat_id: int, args: str) -> None:
        if not args:
            self.state[chat_id] = {"step": "sub_city"}
            await self.api.send(chat_id, "⏰ Для якого міста надсилати щоденний прогноз?")
            return
        parts = args.split()
        hour = None
        if re.fullmatch(r"\d{1,2}(:00)?", parts[-1]):
            hour = int(parts.pop().split(":")[0])
            if not 0 <= hour <= 23:
                raise UserError("Година має бути від 0 до 23.")
        city = await self._find_city(" ".join(parts))
        if hour is None:
            self.state[chat_id] = {"step": "sub_hour", "city": city}
            await self.api.send(chat_id, f"📍 {city.name}. О котрій надсилати прогноз?",
                                kb.hours_kb())
        else:
            await self._save_subscription(chat_id, city, hour)

    async def _save_subscription(self, chat_id: int, city: City, hour: int) -> None:
        self.storage.upsert(chat_id, city, hour)
        self.state.pop(chat_id, None)
        await self.api.send(
            chat_id,
            f"✅ Готово! Щодня о {hour:02d}:00 надсилатиму погоду в місті {city.name} "
            "і підказку, що взяти з собою.\n"
            "Якщо вдень очікуватиметься небезпечна погода — надішлю попередження.",
            kb.MAIN_MENU)

    async def _subscription_menu(self, chat_id: int) -> None:
        sub = self.storage.get(chat_id)
        if not sub:
            self.state[chat_id] = {"step": "sub_city"}
            await self.api.send(chat_id, "⏰ Щоденна розсилка ще не налаштована.\n"
                                         "Для якого міста надсилати прогноз?")
            return
        await self.api.send(chat_id, f"⏰ Ваша підписка: {sub.city.name}, щодня о {sub.hour:02d}:00",
                            kb.subscription_kb())

    async def _subscription_action(self, chat_id: int, value: str) -> None:
        sub = self.storage.get(chat_id)
        if value == "off":
            await self._unsubscribe(chat_id)
        elif not sub:
            await self.api.send(chat_id, "Підписки немає. Налаштуйте: /subscribe")
        elif value == "now":
            await self._send_morning(sub)
        elif value == "city":
            self.state[chat_id] = {"step": "sub_city"}
            await self.api.send(chat_id, "🏙 Напишіть нове місто.")
        elif value == "hour":
            self.state[chat_id] = {"step": "sub_hour", "city": sub.city}
            await self.api.send(chat_id, "🕐 Оберіть новий час:", kb.hours_kb())

    async def _unsubscribe(self, chat_id: int) -> None:
        removed = self.storage.delete(chat_id)
        await self.api.send(chat_id, "🔕 Щоденну розсилку вимкнено." if removed
                            else "У вас немає активної підписки.", kb.MAIN_MENU)

    # ------------------------------------------------------------------ симуляція
    async def _simulation_menu(self, chat_id: int) -> None:
        await self.api.send(chat_id, "🧪 Оберіть, яку «відповідь API» імітувати.\n"
                                     "Бот проаналізує її так само, як справжній прогноз:",
                            kb.simulation_kb())

    async def _send_simulation(self, chat_id: int, name: str) -> None:
        days = validate_forecast(scenario_forecast(name))
        alerts = build_alerts(days)
        text = format_today_message(DEMO_CITY, days[0], build_checklist(days), alerts,
                                    f"🧪 СИМУЛЯЦІЯ: {SCENARIOS[name]['title']}")
        await self.api.send(chat_id, text)
        if has_severe(alerts):
            await self.api.send(chat_id, format_alert_message(DEMO_CITY, alerts))

    # ------------------------------------------------------------------ планувальник
    async def _send_morning(self, sub: Subscription) -> None:
        alerts = await self._send_today(sub.chat_id, sub.city, "☀️ Доброго ранку!")
        today = self.today()
        self.storage.mark_sent(sub.chat_id, today)
        if has_severe(alerts):
            self.storage.mark_alerted(sub.chat_id, today)   # попередження вже було в ранковому

    async def tick(self, now: datetime) -> None:
        """Викликається з головного циклу. Розсилає ранкові прогнози й перевіряє небезпеки."""
        local = now.astimezone(self.tz)
        today = local.date()
        watch_due = self._last_watch is None or now - self._last_watch >= self.watch_interval

        for sub in self.storage.all():
            try:
                if local.hour == sub.hour and sub.last_sent != today:
                    log.info("розсилка: chat %s (%s)", sub.chat_id, sub.city.name)
                    await self._send_morning(sub)
                elif watch_due and sub.last_alert != today and 6 <= local.hour <= 21:
                    days = await self._forecast(sub.city, today, today)
                    alerts = build_alerts(days)
                    if has_severe(alerts):
                        log.info("попередження: chat %s (%s)", sub.chat_id, sub.city.name)
                        await self.api.send(sub.chat_id, format_alert_message(sub.city, alerts))
                        self.storage.mark_alerted(sub.chat_id, today)
            except Exception as e:   # одна помилка не повинна зупиняти розсилку іншим
                log.warning("помилка для chat %s: %s", sub.chat_id, e)

        if watch_due:
            self._last_watch = now
