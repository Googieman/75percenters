"""Application configuration with environment-specific safety checks."""

from functools import lru_cache
from typing import Literal

from pydantic import ValidationInfo, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

Environment = Literal["development", "test", "production"]


class Settings(BaseSettings):
    """Validated runtime settings loaded from the SRM_TRACKER_ environment prefix."""

    model_config = SettingsConfigDict(
        env_prefix="SRM_TRACKER_",
        env_file=".env",
        extra="ignore",
    )

    environment: Environment = "development"
    database_url: str
    frontend_origin: str

    @field_validator("frontend_origin")
    @classmethod
    def production_origin_must_use_https(cls, value: str, info: ValidationInfo) -> str:
        """Disallow insecure browser origins in production."""
        environment = info.data.get("environment")
        if environment == "production" and not value.startswith("https://"):
            raise ValueError("Production frontend origin must use HTTPS")
        return value.rstrip("/")


@lru_cache
def get_settings() -> Settings:
    """Return the process-wide validated settings instance."""
    return Settings()  # type: ignore[call-arg]  # Required values are read from the environment.
