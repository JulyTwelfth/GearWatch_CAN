from functools import lru_cache

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    app_name: str = "GearWatch Canada"
    app_env: str = "development"
    debug: bool = False
    database_url: str = "postgresql+psycopg://gearwatch:gearwatch@localhost:5432/gearwatch"
    http_timeout_seconds: float = Field(default=10.0, gt=0)
    http_max_retries: int = Field(default=2, ge=0, le=5)
    http_backoff_seconds: float = Field(default=0.5, ge=0, le=30)
    http_min_interval_seconds: float = Field(default=2.0, ge=0)
    http_user_agent: str = "GearWatchCanada/0.1 (scheduled portfolio project)"
    arcteryx_outlet_product_urls: str = ""
    collection_interval_seconds: int = Field(default=21_600, ge=300, le=604_800)
    collection_run_on_startup: bool = True

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        env_prefix="GEARWATCH_",
        extra="ignore",
    )

    def configured_arcteryx_outlet_urls(self) -> tuple[str, ...]:
        """Return unique, explicitly configured product URLs in stable order."""
        urls = (value.strip() for value in self.arcteryx_outlet_product_urls.split(","))
        return tuple(dict.fromkeys(url for url in urls if url))


@lru_cache
def get_settings() -> Settings:
    return Settings()
