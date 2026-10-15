from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    telegram_bot_token: str = ""
    telegram_chat_id: str = ""
    telegram_webhook_secret: str = ""
    cron_secret: str = ""
    app_base_url: str = "http://localhost:8000"
    render_external_url: str = ""
    database_url: str = "sqlite:///./data/app.db"
    timezone: str = "Europe/Kyiv"
    watch_interval_minutes: int = 60

    @property
    def public_url(self) -> str:
        return (self.render_external_url or self.app_base_url).rstrip("/")


settings = Settings()
