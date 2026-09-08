"""FastAPI application factory for the SRM Attendance Tracker API."""

from fastapi import FastAPI


def create_app() -> FastAPI:
    """Create the versioned API application without exposing configuration values."""
    app = FastAPI(title="SRM Attendance Tracker API", version="0.1.0")

    @app.get("/api/v1/health")
    def health() -> dict[str, str]:
        return {"status": "ok"}

    return app
