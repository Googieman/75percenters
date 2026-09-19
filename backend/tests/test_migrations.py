import os
from pathlib import Path

import pytest
from alembic import command
from alembic.config import Config
from sqlalchemy import create_engine, inspect


@pytest.mark.integration
def test_migrations_upgrade_downgrade_and_reupgrade() -> None:
    database_url = os.getenv("SRM_TRACKER_TEST_DATABASE_URL")
    if not database_url:
        pytest.skip("SRM_TRACKER_TEST_DATABASE_URL is required for PostgreSQL migration tests")

    backend_root = Path(__file__).parents[1]
    alembic_config = Config(str(backend_root / "alembic.ini"))
    alembic_config.set_main_option("sqlalchemy.url", database_url)
    engine = create_engine(database_url)
    try:
        command.downgrade(alembic_config, "base")
        command.upgrade(alembic_config, "head")
        assert "users" in inspect(engine).get_table_names()
        command.downgrade(alembic_config, "base")
        assert "users" not in inspect(engine).get_table_names()
        command.upgrade(alembic_config, "head")
        assert "attendance_snapshots" in inspect(engine).get_table_names()
    finally:
        engine.dispose()
