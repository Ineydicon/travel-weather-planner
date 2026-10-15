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
    timezone: str = "Europe/Kyiv"
    watch_interval_minutes: int = 60   # як часто перевіряти прогноз на небезпечну погоду

    @property
    def sqlite_path(self) -> str:
        return self.database_url.removeprefix("sqlite:///")


settings = Settings()
