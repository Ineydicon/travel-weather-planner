"""Webhook для Telegram: сюди Telegram надсилає повідомлення користувачів боту."""
from fastapi import APIRouter, Header, HTTPException, Request

from app.config import settings

router = APIRouter()


@router.post("/telegram/webhook", tags=["Telegram"], summary="Приймання оновлень від Telegram",
             include_in_schema=True)
async def telegram_webhook(
    request: Request,
    x_telegram_bot_api_secret_token: str | None = Header(default=None),
):
    if x_telegram_bot_api_secret_token != settings.telegram_webhook_secret:
        raise HTTPException(status_code=403, detail="Невірний секретний токен")
    # Обробка команд /start, /help, /plan — День 4
    return {"ok": True}
