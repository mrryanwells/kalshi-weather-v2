from __future__ import annotations

from functools import lru_cache

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    app_name: str = "kalshi-temp-scanner"
    environment: str = "dev"
    kalshi_base_url: str = "https://api.elections.kalshi.com/trade-api/v2"
    series_tickers: list[str] = Field(default_factory=lambda: ["KXHIGHNY"])
    database_url: str = "sqlite:///./scanner.db"
    scan_interval_seconds: int = 60
    request_timeout_seconds: float = 10.0
    kalshi_ws_url: str = "wss://api.elections.kalshi.com/trade-api/ws/v2"
    websocket_enabled: bool = True


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    return Settings()
