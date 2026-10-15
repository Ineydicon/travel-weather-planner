import asyncio
import logging
import sys
from datetime import datetime, timedelta, timezone

from app.bot.api import TelegramBotApi
from app.bot.logic import COMMANDS, WeatherBot
from app.config import settings
from app.services.notifier import (TelegramError, delete_webhook, get_updates, get_webhook_url,
                                   set_commands)
from app.storage import SubscriptionStorage

POLL_TIMEOUT = 25
MAX_RETRY_DELAY = 60

log = logging.getLogger("bot")


async def main(force: bool = False) -> None:
    token = settings.telegram_bot_token
    if not token:
        print("ПОМИЛКА: у файлі .env не задано TELEGRAM_BOT_TOKEN.")
        return

    storage = SubscriptionStorage(settings.database_url)
    bot = WeatherBot(TelegramBotApi(token), storage, tz=settings.timezone,
                     watch_interval=timedelta(minutes=settings.watch_interval_minutes))

    try:
        if (url := await get_webhook_url(token)) and not force:
            print(f"Бот уже працює в хмарі (webhook: {url}).\n"
                  "Локальний запуск відключить хмарного бота. Якщо це потрібно: python bot.py --force\n"
                  "Щоб повернути хмарного бота - перезапустіть сервіс на Render (Manual Deploy).")
            return
        await delete_webhook(token)
        await set_commands(token, COMMANDS)
    except TelegramError as e:
        print(f"ПОМИЛКА Telegram: {e}")
        return

    log.info("Бот запущено. Підписок у базі: %d. Зупинка: Ctrl+C", len(storage.all()))
    offset = None
    retry_delay = 5

    while True:
        try:
            updates = await get_updates(token, offset, timeout=POLL_TIMEOUT)
            retry_delay = 5
        except TelegramError as e:
            log.warning("%s Повтор через %d с.", e, retry_delay)
            await asyncio.sleep(retry_delay)
            retry_delay = min(retry_delay * 2, MAX_RETRY_DELAY)
            updates = []

        for update in updates:
            offset = update["update_id"] + 1
            try:
                await bot.handle_update(update)
            except Exception as e:
                log.exception("Помилка обробки оновлення: %s", e)

        try:
            await bot.tick(datetime.now(timezone.utc))
        except Exception as e:
            log.exception("Помилка планувальника: %s", e)


if __name__ == "__main__":
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")
    logging.basicConfig(level=logging.INFO, format="%(asctime)s  %(message)s",
                        datefmt="%H:%M:%S", stream=sys.stdout)
    logging.getLogger("httpx").setLevel(logging.WARNING)  # httpx логує URL разом із токеном
    try:
        asyncio.run(main(force="--force" in sys.argv))
    except KeyboardInterrupt:
        print("\nБота зупинено.")
