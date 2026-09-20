"""Local-only database support for the disposable Playwright flow."""

from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path
from urllib.parse import urlsplit

from sqlalchemy import create_engine, select
from sqlalchemy.orm import Session, sessionmaker

ROOT = Path(__file__).parents[1]
sys.path.insert(0, str(ROOT / "src"))

from srm_tracker.admin import bootstrap_account  # noqa: E402
from srm_tracker.db_models import AttendanceSnapshot, ConnectorDevice, Subject  # noqa: E402
from srm_tracker.db_models import Session as AuthSession  # noqa: E402
from srm_tracker.time import utc_now  # noqa: E402


def factory() -> sessionmaker[Session]:
    database_url = os.environ.get("SRM_TRACKER_DATABASE_URL")
    if not database_url or not database_url.startswith("postgresql+psycopg://"):
        raise RuntimeError("refusing database support without the runner-owned PostgreSQL URL")
    parsed = urlsplit(database_url)
    expected_port = os.environ.get("E2E_DATABASE_PORT")
    expected_database = os.environ.get("E2E_DATABASE_NAME")
    container_name = os.environ.get("E2E_CONTAINER_NAME")
    expected_label = os.environ.get("E2E_CONTAINER_LABEL")
    if (
        parsed.hostname not in {"127.0.0.1", "localhost"}
        or not expected_port
        or str(parsed.port) != expected_port
        or parsed.path.removeprefix("/") != expected_database
        or not container_name
        or not expected_label
    ):
        raise RuntimeError("refusing database support outside the runner-owned loopback database")
    label = subprocess.run(
        [
            "docker",
            "inspect",
            "--format",
            '{{index .Config.Labels "com.srm-tracker.e2e"}}',
            container_name,
        ],
        check=False,
        capture_output=True,
        text=True,
    )
    if label.returncode != 0 or label.stdout.strip() != expected_label:
        raise RuntimeError("refusing database support for an unowned container")
    return sessionmaker(
        bind=create_engine(database_url, pool_pre_ping=True),
        expire_on_commit=False,
    )


def main(command: str) -> None:
    sessions = factory()
    with sessions() as session:
        if command == "bootstrap":
            bootstrap_account(
                session,
                os.environ["E2E_ACCOUNT_EMAIL"],
                os.environ["E2E_ACCOUNT_PASSWORD"],
            )
            print(json.dumps({"ok": True}))
        elif command == "expire-session":
            for auth_session in session.scalars(select(AuthSession)).all():
                auth_session.invalidated_at = utc_now()
            session.commit()
            print(json.dumps({"ok": True}))
        elif command == "state":
            subjects = session.scalars(select(Subject).order_by(Subject.code)).all()
            print(json.dumps({
                "snapshots": session.query(AttendanceSnapshot).count(),
                "subjects": [
                    {
                        "code": subject.code,
                        "total_hours": subject.total_hours,
                        "attended_hours": subject.attended_hours,
                        "absent_hours": subject.absent_hours,
                    }
                    for subject in subjects
                ],
                "devices": session.query(ConnectorDevice).count(),
            }))
        else:
            raise SystemExit(f"unsupported e2e support command: {command}")


if __name__ == "__main__":
    if len(sys.argv) != 2:
        raise SystemExit("usage: e2e_support.py bootstrap|expire-session|state")
    main(sys.argv[1])
