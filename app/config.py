"""Application settings loaded from environment via pydantic-settings."""
from __future__ import annotations

from functools import lru_cache

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    app_env: str = Field(default="development", alias="APP_ENV")
    secret_key: str = Field(default="change-me-in-production-this-must-be-long-and-random", alias="SECRET_KEY")
    database_url: str = Field(default="sqlite:///./shopdesk.db", alias="DATABASE_URL")
    shop_timezone: str = Field(default="Asia/Dhaka", alias="SHOP_TIMEZONE")
    currency_symbol: str = Field(default="৳", alias="CURRENCY_SYMBOL")
    shop_name: str = Field(default="My Shop", alias="SHOP_NAME")
    shop_address: str = Field(default="", alias="SHOP_ADDRESS")
    shop_phone: str = Field(default="", alias="SHOP_PHONE")
    invoice_footer: str = Field(default="Thank you for your purchase!", alias="INVOICE_FOOTER")
    login_rate_limit_per_minute: int = Field(default=5, alias="LOGIN_RATE_LIMIT_PER_MINUTE")

    @property
    def is_production(self) -> bool:
        return self.app_env.lower() == "production"

    @property
    def is_sqlite(self) -> bool:
        return self.database_url.startswith("sqlite")


DEFAULT_SECRET_KEY = "change-me-in-production-this-must-be-long-and-random"  # noqa: S105


@lru_cache
def get_settings() -> Settings:
    return Settings()


def reset_settings_cache() -> None:
    """Clear the cached settings (used in tests)."""
    get_settings.cache_clear()
