import base64

import pytest
from pydantic import ValidationError

from srm_tracker.config import Settings, get_settings


def test_reads_development_settings() -> None:
    settings = Settings(
        environment="development",
        database_url="postgresql+psycopg://user:password@localhost:5432/srm_tracker",
        frontend_origin="http://localhost:5173",
    )

    assert settings.environment == "development"
    assert settings.database_url == "postgresql+psycopg://user:password@localhost:5432/srm_tracker"
    assert settings.frontend_origin == "http://localhost:5173"


def test_supports_request_driven_sync_execution() -> None:
    settings = Settings(sync_execution_mode="on_demand")

    assert settings.sync_execution_mode == "on_demand"


def test_hosted_staging_requires_https_and_encryption_key() -> None:
    with pytest.raises(ValidationError, match="HTTPS"):
        Settings(environment="staging", frontend_origin="http://localhost:5173")

    settings = Settings(
        environment="staging",
        frontend_origin="https://staging.example.com",
        session_encryption_key=base64.urlsafe_b64encode(bytes(range(32))).decode(),
    )
    assert settings.environment == "staging"


def test_rejects_http_frontend_origin_in_production() -> None:
    with pytest.raises(ValidationError, match="HTTPS"):
        Settings(
            environment="production",
            database_url="postgresql+psycopg://user:password@db:5432/srm_tracker",
            frontend_origin="http://localhost:5173",
        )


def test_production_requires_separate_session_encryption_key() -> None:
    with pytest.raises(ValidationError, match="encryption key"):
        Settings(
            environment="production",
            database_url="postgresql+psycopg://user:password@db:5432/srm_tracker",
            frontend_origin="https://tracker.example.com",
        )


def test_rejects_invalid_session_encryption_key_material() -> None:
    with pytest.raises(ValidationError, match="32 bytes"):
        Settings(session_encryption_key="not-a-session-key")


def test_reads_prefixed_environment_through_cached_loader(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("SRM_TRACKER_DATABASE_URL", "postgresql+psycopg://user:password@db:5432/srm")
    monkeypatch.setenv("SRM_TRACKER_FRONTEND_ORIGIN", "http://localhost:5173/")
    get_settings.cache_clear()

    settings = get_settings()

    assert settings.database_url.endswith("/srm")
    assert settings.frontend_origin == "http://localhost:5173"
