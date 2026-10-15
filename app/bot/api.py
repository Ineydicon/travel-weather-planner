"""Адаптер Telegram Bot API для логіки бота."""
from app.services import notifier


class TelegramBotApi:
    def __init__(self, token: str):
        self.token = token

    async def send(self, chat_id: int, text: str, markup: dict | None = None) -> None:
        await notifier.send_message(self.token, chat_id, text, reply_markup=markup)

    async def answer(self, callback_id: str, text: str = "") -> None:
        try:
            await notifier.answer_callback(self.token, callback_id, text)
        except notifier.TelegramError:
            pass   # не критично: просто зникне «годинник» на кнопці
