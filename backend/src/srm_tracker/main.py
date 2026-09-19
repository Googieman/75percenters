"""FastAPI application factory for the SRM Attendance Tracker API."""

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from sqlalchemy.engine import Engine
from sqlalchemy.orm import Session as DbSession
from sqlalchemy.orm import sessionmaker

from srm_tracker.auth import router as auth_router
from srm_tracker.config import Settings, get_settings
from srm_tracker.db import session_factory_for_engine


def create_app(
    settings: Settings | None = None,
    session_factory: sessionmaker[DbSession] | None = None,
    engine: Engine | None = None,
) -> FastAPI:
    """Create the versioned API application without exposing configuration values."""
    settings = settings or get_settings()
    app = FastAPI(title="SRM Attendance Tracker API", version="0.1.0")
    app.state.settings = settings
    app.state.session_factory = session_factory
    app.state.database_engine = engine
    if engine is not None:
        app.state.session_factory = session_factory_for_engine(engine)

    app.add_middleware(
        CORSMiddleware,
        allow_origins=[settings.frontend_origin],
        allow_credentials=True,
        allow_methods=["GET", "POST", "PATCH", "DELETE", "OPTIONS"],
        allow_headers=["Content-Type", "Authorization", "X-CSRF-Token"],
    )
    app.include_router(auth_router)

    @app.get("/api/v1/health")
    def health() -> dict[str, str]:
        return {"status": "ok"}

    return app
