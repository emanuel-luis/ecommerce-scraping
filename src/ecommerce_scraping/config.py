"""Settings read from ECOMMERCE_* environment variables and an optional .env file."""

from pathlib import Path

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict

from ecommerce_scraping import __version__


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_prefix="ECOMMERCE_", env_file=".env", extra="ignore")

    data_dir: Path = Path("data")
    user_agent: str = Field(
        default_factory=lambda: (
            f"ecommerce-scraping/{__version__} (+https://github.com/emanuel-luis/ecommerce-scraping)"
        )
    )
    download_delay_s: float = Field(default=3, ge=0)
    store_base_urls: dict[str, str] = {}  # JSON in the environment; replaces a store's base URL
    default_limit: int = Field(default=20, ge=1)
    log_level: str = "INFO"
