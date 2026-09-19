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
    database_url: str = "postgresql+psycopg://srm_tracker:srm_tracker@localhost:5433/srm_tracker"
    frontend_origin: str = "http://localhost:5173"
    session_cookie_name: str = "srm_tracker_session"
    session_ttl_days: int = 7
    pairing_ttl_minutes: int = 10
    login_rate_limit_attempts: int = 5
    pairing_rate_limit_attempts: int = 10
    rate_limit_window_seconds: int = 900

    @field_validator("frontend_origin")
    @classmethod
    def production_origin_must_use_https(cls, value: str, info: ValidationInfo) -> str:
        """Disallow insecure browser origins in production."""
        environment = info.data.get("environment")
        if environment == "production" and not value.startswith("https://"):
            raise ValueError("Production frontend origin must use HTTPS")
        return value.rstrip("/")

    @field_validator("session_ttl_days", "pairing_ttl_minutes", "rate_limit_window_seconds")
    @classmethod
    def positive_duration(cls, value: int) -> int:
        if value <= 0:
            raise ValueError("duration settings must be positive")
        return value

    @field_validator("login_rate_limit_attempts", "pairing_rate_limit_attempts")
    @classmethod
    def positive_rate_limit(cls, value: int) -> int:
        if value <= 0:
            raise ValueError("rate limit settings must be positive")
        return value


@lru_cache
def get_settings() -> Settings:
    """Return the process-wide validated settings instance."""
    return Settings()
