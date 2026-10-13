"""Налаштування застосунку. Значення читаються з файлу .env / змінних оточення,
тому секрети (токени) ніколи не зберігаються в коді."""
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    telegram_bot_token: str = ""
    telegram_chat_id: str = ""
    telegram_webhook_secret: str = ""
    app_base_url: str = "http://localhost:8000"
    database_url: str = "sqlite:///./data/app.db"


settings = Settings()
