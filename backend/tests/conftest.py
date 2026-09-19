"""Shared backend test configuration."""

import asyncio
import os
from collections.abc import Iterator
from pathlib import Path
from typing import Any

import httpx
import pytest
from alembic import command
from alembic.config import Config
from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker

FIXTURES_DIR = Path(__file__).parent / "fixtures"


@pytest.fixture
def valid_html() -> str:
    return (FIXTURES_DIR / "attendance-valid.html").read_text(encoding="utf-8")


@pytest.fixture
def login_html() -> str:
    return (FIXTURES_DIR / "attendance-login.html").read_text(encoding="utf-8")


@pytest.fixture
def malformed_html() -> str:
    return (FIXTURES_DIR / "attendance-malformed.html").read_text(encoding="utf-8")


@pytest.fixture
def database_session_factory() -> Iterator[sessionmaker[Session]]:
    database_url = os.getenv("SRM_TRACKER_TEST_DATABASE_URL")
    if not database_url:
        pytest.skip("SRM_TRACKER_TEST_DATABASE_URL is required for API integration tests")

    backend_root = Path(__file__).parents[1]
    alembic_config = Config(str(backend_root / "alembic.ini"))
    alembic_config.set_main_option("sqlalchemy.url", database_url)
    command.downgrade(alembic_config, "base")
    command.upgrade(alembic_config, "head")
    engine = create_engine(database_url, pool_pre_ping=True)
    factory = sessionmaker(bind=engine, autoflush=False, expire_on_commit=False)
    try:
        yield factory
    finally:
        engine.dispose()


@pytest.fixture
def app_client(database_session_factory: sessionmaker[Session]) -> Iterator[Any]:
    from srm_tracker.config import Settings
    from srm_tracker.main import create_app

    settings = Settings(
        database_url=os.environ["SRM_TRACKER_TEST_DATABASE_URL"],
        frontend_origin="http://localhost:5173",
        login_rate_limit_attempts=5,
        pairing_rate_limit_attempts=10,
    )
    app = create_app(settings=settings, session_factory=database_session_factory)

    class Client:
        def __init__(self) -> None:
            self.cookies: dict[str, str] = {}

        def request(self, method: str, url: str, **kwargs: Any) -> httpx.Response:
            async def send() -> httpx.Response:
                transport = httpx.ASGITransport(app=app)
                async with httpx.AsyncClient(
                    transport=transport,
                    base_url="http://testserver",
                    cookies=self.cookies,
                ) as client:
                    return await client.request(method, url, **kwargs)

            response = asyncio.run(send())
            self.cookies.update(response.cookies)
            return response

    yield Client()
