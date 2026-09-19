"""SQLAlchemy engine, declarative base, and request session helpers."""

from collections.abc import Iterator
from typing import Any

from sqlalchemy import MetaData, create_engine
from sqlalchemy.engine import Engine
from sqlalchemy.orm import DeclarativeBase, sessionmaker
from sqlalchemy.orm import Session as DbSession

from srm_tracker.config import Settings


class Base(DeclarativeBase):
    """Base class for all application tables."""

    metadata = MetaData(
        naming_convention={
            "ix": "ix_%(column_0_label)s",
            "uq": "uq_%(table_name)s_%(column_0_name)s",
            "ck": "ck_%(table_name)s_%(constraint_name)s",
            "fk": "fk_%(table_name)s_%(column_0_name)s_%(referred_table_name)s",
            "pk": "pk_%(table_name)s",
        }
    )


def create_engine_from_settings(settings: Settings) -> Engine:
    """Create a SQLAlchemy engine without connecting during construction."""
    return create_engine(settings.database_url, pool_pre_ping=True)


def session_factory_for_engine(engine: Engine) -> sessionmaker[DbSession]:
    """Create non-expiring request sessions bound to an engine."""
    return sessionmaker(bind=engine, autoflush=False, expire_on_commit=False)


def get_db(session_factory: sessionmaker[DbSession]) -> Iterator[DbSession]:
    """Yield one database session and always close it after the request."""
    session = session_factory()
    try:
        yield session
    finally:
        session.close()


def model_dict(model: Any) -> dict[str, Any]:
    """Return a small typed escape hatch for CLI/debug callers, never logs it."""
    return {column.name: getattr(model, column.name) for column in model.__table__.columns}
