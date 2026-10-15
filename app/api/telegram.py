import logging

from fastapi import APIRouter, Header, HTTPException, Request

from app.config import settings

router = APIRouter()
log = logging.getLogger("bot")


@router.post("/telegram/webhook", tags=["Telegram"], summary="Приймання оновлень від Telegram")
async def telegram_webhook(
    request: Request,
    x_telegram_bot_api_secret_token: str | None = Header(default=None),
):
    if (not settings.telegram_webhook_secret
            or x_telegram_bot_api_secret_token != settings.telegram_webhook_secret):
        raise HTTPException(status_code=403, detail="Невірний секретний токен")
    update = await request.json()
    try:
        await request.app.state.bot.handle_update(update)
    except Exception as e:  # відповідаємо 200, інакше Telegram повторюватиме запит
        log.exception("Помилка обробки оновлення: %s", e)
    return {"ok": True}
