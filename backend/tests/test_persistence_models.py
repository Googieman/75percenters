from datetime import UTC, datetime
from decimal import Decimal

from sqlalchemy import inspect

from srm_tracker.db import Base
from srm_tracker.db_models import (
    AttendanceSnapshot,
    ConnectorDevice,
    PairingCode,
    RateLimitBucket,
    Session,
    Subject,
    User,
)


def test_persistence_metadata_contains_owned_tables_and_relationships() -> None:
    expected_tables = {
        "users",
        "sessions",
        "subjects",
        "attendance_snapshots",
        "pairing_codes",
        "connector_devices",
        "rate_limit_buckets",
    }

    assert expected_tables == set(Base.metadata.tables)
    assert User.subjects.property.mapper.class_ is Subject
    assert Subject.snapshots.property.mapper.class_ is AttendanceSnapshot
    assert User.devices.property.mapper.class_ is ConnectorDevice
    assert User.pairing_codes.property.mapper.class_ is PairingCode
    assert User.sessions.property.mapper.class_ is Session
    assert User.rate_limits.property.mapper.class_ is RateLimitBucket


def test_subject_code_is_unique_per_owner() -> None:
    constraints = inspect(Subject).local_table.constraints

    assert any(
        constraint.name == "uq_subject_user_code"
        and {column.name for column in constraint.columns} == {"user_id", "code"}
        for constraint in constraints
    )


def test_percentage_and_timestamp_columns_are_utc_compatible() -> None:
    assert Subject.__table__.c.source_percentage.type.scale == 2
    assert User.__table__.c.attendance_target.default.arg == Decimal("75.00")
    assert User.__table__.c.created_at.type.timezone is True
    assert datetime.now(UTC).utcoffset() is not None
