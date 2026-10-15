import httpx

API_URL = "https://api.telegram.org/bot{token}/{method}"


class TelegramError(Exception):
    pass


async def _call(token: str, method: str, payload: dict,
                client: httpx.AsyncClient | None = None, timeout: float = 10.0) -> dict:
    url = API_URL.format(token=token, method=method)
    own = client is None
    c = client or httpx.AsyncClient(timeout=httpx.Timeout(timeout))
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
                       client: httpx.AsyncClient | None = None,
                       reply_markup: dict | None = None) -> None:
    payload = {"chat_id": chat_id, "text": text}
    if reply_markup:
        payload["reply_markup"] = reply_markup
    await _call(token, "sendMessage", payload, client)


async def answer_callback(token: str, callback_id: str, text: str = "") -> None:
    await _call(token, "answerCallbackQuery", {"callback_query_id": callback_id, "text": text})


async def get_updates(token: str, offset: int | None = None, timeout: int = 25) -> list[dict]:
    payload = {"timeout": timeout, "allowed_updates": ["message", "callback_query"]}
    if offset is not None:
        payload["offset"] = offset
    data = await _call(token, "getUpdates", payload, timeout=timeout + 10)
    return data.get("result", [])


async def set_webhook(token: str, url: str, secret: str) -> None:
    await _call(token, "setWebhook", {"url": url, "secret_token": secret,
                                      "allowed_updates": ["message", "callback_query"]})


async def get_webhook_url(token: str) -> str:
    data = await _call(token, "getWebhookInfo", {})
    return data.get("result", {}).get("url", "")


async def delete_webhook(token: str) -> None:
    await _call(token, "deleteWebhook", {})


async def set_commands(token: str, commands: list[tuple[str, str]]) -> None:
    await _call(token, "setMyCommands",
                {"commands": [{"command": c, "description": d} for c, d in commands]})


async def find_chats(token: str, client: httpx.AsyncClient | None = None) -> list[tuple[int, str]]:
    data = await _call(token, "getUpdates", {}, client)
    chats: dict[int, str] = {}
    for update in data.get("result", []):
        chat = (update.get("message") or {}).get("chat")
        if chat:
            name = chat.get("username") or chat.get("first_name") or chat.get("title") or ""
            chats[chat["id"]] = name
    return list(chats.items())
