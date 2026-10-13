"""Клієнт Telegram Bot API (API 2): надсилання повідомлень.

Токен передається параметром і НІКОЛИ не виводиться в повідомленнях про помилки.
"""
import httpx

API_URL = "https://api.telegram.org/bot{token}/{method}"
TIMEOUT = httpx.Timeout(10.0)


class TelegramError(Exception):
    """Telegram недоступний або відхилив запит."""


async def _call(token: str, method: str, payload: dict,
                client: httpx.AsyncClient | None = None) -> dict:
    url = API_URL.format(token=token, method=method)
    own = client is None
    c = client or httpx.AsyncClient(timeout=TIMEOUT)
    try:
        response = await c.post(url, json=payload)
    except httpx.TimeoutException:
        raise TelegramError("Telegram не відповідає (тайм-аут). Спробуйте пізніше.")
    except httpx.RequestError as e:
        raise TelegramError(f"Немає з'єднання з Telegram ({type(e).__name__}). Перевірте інтернет.")
    finally:
        if own:
            await c.aclose()

    try:
        data = response.json()
    except ValueError:
        data = {}
    description = data.get("description", "")

    if response.status_code == 200 and data.get("ok"):
        return data
    if response.status_code in (401, 404):
        raise TelegramError("Невірний токен бота. Перевірте TELEGRAM_BOT_TOKEN у файлі .env.")
    if response.status_code == 400 and "chat not found" in description:
        raise TelegramError("Чат не знайдено. Напишіть боту /start і перевірте TELEGRAM_CHAT_ID.")
    if response.status_code == 403:
        raise TelegramError("Бот не може писати цьому користувачу (бота заблоковано "
                            "або користувач ще не натиснув /start).")
    if response.status_code == 429:
        raise TelegramError("Перевищено ліміт повідомлень Telegram. Спробуйте за хвилину.")
    raise TelegramError(f"Telegram повернув помилку {response.status_code}: {description}")


async def send_message(token: str, chat_id: int | str, text: str,
                       client: httpx.AsyncClient | None = None) -> None:
    await _call(token, "sendMessage", {"chat_id": chat_id, "text": text}, client)


async def find_chats(token: str, client: httpx.AsyncClient | None = None) -> list[tuple[int, str]]:
    """Повертає (chat_id, ім'я) усіх, хто нещодавно писав боту."""
    data = await _call(token, "getUpdates", {}, client)
    chats: dict[int, str] = {}
    for update in data.get("result", []):
        chat = (update.get("message") or {}).get("chat")
        if chat:
            name = chat.get("username") or chat.get("first_name") or chat.get("title") or ""
            chats[chat["id"]] = name
    return list(chats.items())
