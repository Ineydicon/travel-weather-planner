"""Запуск Telegram-бота (локально, режим long polling).

    python bot.py

Головний цикл while True:
  1) забирає нові повідомлення з Telegram (getUpdates чекає до 25 с);
  2) обробляє команди й натискання кнопок;
  3) викликає планувальник: ранкова розсилка та перевірка небезпечної погоди
     (Open-Meteo опитується не частіше ніж раз на годину для кожного підписника,
     відповіді кешуються на 30 хв — ліміти безкоштовного API не порушуються).
Зупинка: Ctrl + C.
"""
import asyncio
import logging
import sys
from datetime import datetime, timedelta, timezone

from app.bot.api import TelegramBotApi
from app.bot.logic import COMMANDS, WeatherBot
from app.config import settings
from app.services.notifier import TelegramError, delete_webhook, get_updates, set_commands
from app.storage import SubscriptionStorage

POLL_TIMEOUT = 25          # секунд очікування нових повідомлень (long polling)
MAX_RETRY_DELAY = 60       # максимальна пауза між повторними спробами при збоях

log = logging.getLogger("bot")


async def main() -> None:
    token = settings.telegram_bot_token
    if not token:
        print("ПОМИЛКА: у файлі .env не задано TELEGRAM_BOT_TOKEN.")
        return

    storage = SubscriptionStorage(settings.sqlite_path)
    bot = WeatherBot(TelegramBotApi(token), storage, tz=settings.timezone,
                     watch_interval=timedelta(minutes=settings.watch_interval_minutes))

    try:
        await delete_webhook(token)
        await set_commands(token, COMMANDS)
    except TelegramError as e:
        print(f"ПОМИЛКА Telegram: {e}")
        return

    log.info("Бот запущено. Підписок у базі: %d. Зупинка: Ctrl+C", len(storage.all()))
    offset = None
    retry_delay = 5

    while True:
        # 1. Нові повідомлення
        try:
            updates = await get_updates(token, offset, timeout=POLL_TIMEOUT)
            retry_delay = 5
        except TelegramError as e:
            log.warning("%s Повтор через %d с.", e, retry_delay)
            await asyncio.sleep(retry_delay)
            retry_delay = min(retry_delay * 2, MAX_RETRY_DELAY)
            updates = []

        # 2. Обробка
        for update in updates:
            offset = update["update_id"] + 1
            try:
                await bot.handle_update(update)
            except Exception as e:   # бот не повинен падати через одне повідомлення
                log.exception("Помилка обробки оновлення: %s", e)

        # 3. Планувальник
        try:
            await bot.tick(datetime.now(timezone.utc))
        except Exception as e:
            log.exception("Помилка планувальника: %s", e)


if __name__ == "__main__":
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")
    logging.basicConfig(level=logging.INFO, format="%(asctime)s  %(message)s",
                        datefmt="%H:%M:%S", stream=sys.stdout)
    logging.getLogger("httpx").setLevel(logging.WARNING)   # не друкувати URL з токеном
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        print("\nБота зупинено.")
