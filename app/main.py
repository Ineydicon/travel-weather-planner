import logging
from contextlib import asynccontextmanager
from datetime import timedelta

from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles

from app.api import routes, telegram
from app.bot.api import TelegramBotApi
from app.bot.logic import COMMANDS, WeatherBot
from app.config import settings
from app.services.notifier import TelegramError, set_commands, set_webhook
from app.storage import SubscriptionStorage

logging.basicConfig(level=logging.INFO, format="%(asctime)s  %(message)s", datefmt="%H:%M:%S")
logging.getLogger("httpx").setLevel(logging.WARNING)  # httpx логує URL разом із токеном
log = logging.getLogger("bot")


async def setup_webhook() -> None:
    if not settings.telegram_webhook_secret:
        log.warning("TELEGRAM_WEBHOOK_SECRET не задано - webhook не налаштовано")
        return
    try:
        await set_webhook(settings.telegram_bot_token, f"{settings.public_url}/telegram/webhook",
                          settings.telegram_webhook_secret)
        await set_commands(settings.telegram_bot_token, COMMANDS)
        log.info("Webhook: %s/telegram/webhook", settings.public_url)
    except TelegramError as e:
        log.warning("Не вдалося налаштувати webhook: %s", e)


@asynccontextmanager
async def lifespan(app: FastAPI):
    storage = SubscriptionStorage(settings.database_url)
    app.state.bot = WeatherBot(TelegramBotApi(settings.telegram_bot_token), storage,
                               tz=settings.timezone,
                               watch_interval=timedelta(minutes=settings.watch_interval_minutes))
    if settings.telegram_bot_token and settings.public_url.startswith("https://"):
        await setup_webhook()
    log.info("Сервіс запущено. База: %s, підписок: %d",
             "PostgreSQL" if storage.is_postgres else "SQLite", len(storage.all()))
    yield


app = FastAPI(
    title="Travel Weather Planner API",
    version=routes.VERSION,
    description="Прогноз погоди, аналіз (статуси-попередження) та чек-ліст речей. "
                "Зовнішні сервіси: Open-Meteo (погода) і Telegram Bot API (бот).",
    lifespan=lifespan,
)

app.include_router(routes.router)
app.include_router(telegram.router)

app.mount("/", StaticFiles(directory="static", html=True), name="static")
