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


def test_rejects_http_frontend_origin_in_production() -> None:
    with pytest.raises(ValidationError, match="HTTPS"):
        Settings(
            environment="production",
            database_url="postgresql+psycopg://user:password@db:5432/srm_tracker",
            frontend_origin="http://localhost:5173",
        )


def test_reads_prefixed_environment_through_cached_loader(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("SRM_TRACKER_DATABASE_URL", "postgresql+psycopg://user:password@db:5432/srm")
    monkeypatch.setenv("SRM_TRACKER_FRONTEND_ORIGIN", "http://localhost:5173/")
    get_settings.cache_clear()

    settings = get_settings()

    assert settings.database_url.endswith("/srm")
    assert settings.frontend_origin == "http://localhost:5173"
