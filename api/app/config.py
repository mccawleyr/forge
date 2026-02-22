from pydantic_settings import BaseSettings
from functools import lru_cache


class Settings(BaseSettings):
    # Database
    database_url: str = "postgresql://postgres:postgres@localhost:5432/forge"

    # Claude API
    anthropic_api_key: str = ""

    # OpenAI (fallback)
    openai_api_key: str = ""

    # USDA FoodData Central
    usda_api_key: str = ""

    # App settings
    debug: bool = False

    # Bot notification URL (for reminders)
    bot_notification_url: str = "http://forge-bot:8080"

    class Config:
        env_file = ".env"


@lru_cache
def get_settings() -> Settings:
    return Settings()
