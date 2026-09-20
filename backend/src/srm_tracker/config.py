"""Application configuration with environment-specific safety checks."""

from functools import lru_cache
from typing import Literal

from pydantic import ValidationInfo, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

from srm_tracker.acquisition_crypto import SessionCipher, SessionCipherError

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
    session_encryption_key: str | None = None
    session_encryption_key_version: int = 1
    session_encryption_read_keys: str | None = None
    acquisition_enabled: bool = False
    web_push_public_key: str | None = None
    web_push_private_key: str | None = None
    web_push_subject: str | None = None
    sync_poll_interval_seconds: int = 30
    sync_minimum_interval_minutes: int = 5
    sync_hourly_interval_minutes: int = 60

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

    @field_validator("session_encryption_key")
    @classmethod
    def production_requires_encryption_key(
        cls, value: str | None, info: ValidationInfo
    ) -> str | None:
        if info.data.get("environment") == "production" and not value:
            raise ValueError("Production requires a session encryption key")
        if value:
            try:
                SessionCipher.from_base64(value)
            except SessionCipherError as error:
                raise ValueError(
                    "session encryption key must be URL-safe base64 for 32 bytes"
                ) from error
        return value

    @field_validator(
        "session_encryption_key_version",
        "sync_poll_interval_seconds",
        "sync_minimum_interval_minutes",
        "sync_hourly_interval_minutes",
    )
    @classmethod
    def positive_acquisition_setting(cls, value: int) -> int:
        if value <= 0:
            raise ValueError("acquisition settings must be positive")
        return value


@lru_cache
def get_settings() -> Settings:
    """Return the process-wide validated settings instance."""
    return Settings()
