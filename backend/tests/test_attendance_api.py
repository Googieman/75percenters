from concurrent.futures import ThreadPoolExecutor

from srm_tracker.admin import bootstrap_account
from srm_tracker.attendance_service import process_upload
from srm_tracker.db_models import AttendanceSnapshot, ConnectorDevice
from srm_tracker.schemas import AttendanceUpload, SubjectUpload
from srm_tracker.security import hash_opaque_token

RECORDS = [
    {
        "code": "CSE1",
        "subject": "Algorithms",
        "total_hours": 23,
        "attended_hours": 16,
        "absent_hours": 7,
        "source_percentage": "69.57",
    },
    {
        "code": "MAT1",
        "subject": "Mathematics",
        "total_hours": 10,
        "attended_hours": 8,
        "absent_hours": 2,
        "source_percentage": "80",
    },
]


def _login(client: object) -> str:
    response = client.request(  # type: ignore[union-attr]
        "POST",
        "/api/v1/auth/login",
        json={"email": "owner@example.com", "password": "a-very-long-password"},
    )
    assert response.status_code == 200
    return response.json()["csrf_token"]


def _pair(client: object, csrf: str) -> str:
    code = client.request(  # type: ignore[union-attr]
        "POST", "/api/v1/pairing-codes", headers={"X-CSRF-Token": csrf}
    ).json()["code"]
    response = client.request(  # type: ignore[union-attr]
        "POST", "/api/v1/connector/pair", json={"code": code}
    )
    assert response.status_code == 200
    return response.json()["device_token"]


def _setup(client: object, database_session_factory: object) -> tuple[str, str]:
    with database_session_factory() as session:  # type: ignore[operator]
        bootstrap_account(session, "owner@example.com", "a-very-long-password")
    csrf = _login(client)
    return csrf, _pair(client, csrf)


def test_first_upload_is_persisted_and_reads_include_guidance(
    database_session_factory: object,
    app_client: object,
) -> None:
    csrf, device_token = _setup(app_client, database_session_factory)
    upload = app_client.request(  # type: ignore[union-attr]
        "POST",
        "/api/v1/connector/attendance",
        headers={"Authorization": f"Bearer {device_token}"},
        json={"subjects": RECORDS},
    )
    assert upload.status_code == 200
    assert upload.json()["snapshots_created"] == 2

    attendance = app_client.request("GET", "/api/v1/attendance")  # type: ignore[union-attr]
    assert attendance.status_code == 200
    body = attendance.json()
    assert body["attendance_target"] == 75
    assert len(body["subjects"]) == 2
    assert body["overall"]["current_percentage"] == 72.73
    assert body["subjects"][0]["guidance"]["additional_attended_hours"] == 5
    assert body["last_successful_sync"]
    assert csrf


def test_unchanged_retry_updates_last_seen_without_new_snapshot(
    database_session_factory: object,
    app_client: object,
) -> None:
    _csrf, device_token = _setup(app_client, database_session_factory)
    headers = {"Authorization": f"Bearer {device_token}"}
    first = app_client.request(  # type: ignore[union-attr]
        "POST", "/api/v1/connector/attendance", headers=headers, json={"subjects": RECORDS}
    )
    second = app_client.request(  # type: ignore[union-attr]
        "POST", "/api/v1/connector/attendance", headers=headers, json={"subjects": RECORDS}
    )
    assert first.json()["snapshots_created"] == 2
    assert second.json()["snapshots_created"] == 0
    with database_session_factory() as session:  # type: ignore[operator]
        assert session.query(AttendanceSnapshot).count() == 2
        assert session.query(ConnectorDevice).one().last_seen_at is not None


def test_changed_totals_including_downward_correction_create_history(
    database_session_factory: object,
    app_client: object,
) -> None:
    _csrf, device_token = _setup(app_client, database_session_factory)
    headers = {"Authorization": f"Bearer {device_token}"}
    app_client.request(  # type: ignore[union-attr]
        "POST", "/api/v1/connector/attendance", headers=headers, json={"subjects": RECORDS}
    )
    corrected = [RECORDS[0] | {"total_hours": 24, "attended_hours": 15, "absent_hours": 9}]
    changed = app_client.request(  # type: ignore[union-attr]
        "POST", "/api/v1/connector/attendance", headers=headers, json={"subjects": corrected}
    )
    assert changed.json()["snapshots_created"] == 1
    attendance = app_client.request("GET", "/api/v1/attendance")  # type: ignore[union-attr]
    assert attendance.json()["subjects"][0]["attended_hours"] == 15
    assert len(attendance.json()["subjects"]) == 2

    subject_id = attendance.json()["subjects"][0]["id"]
    history = app_client.request(  # type: ignore[union-attr]
        "GET", f"/api/v1/subjects/{subject_id}/history?limit=1"
    )
    assert history.status_code == 200
    assert len(history.json()["items"]) == 1
    assert history.json()["items"][0]["attended_hours"] == 15
    assert history.json()["next_cursor"]
    older = app_client.request(  # type: ignore[union-attr]
        "GET",
        f"/api/v1/subjects/{subject_id}/history?limit=2&cursor={history.json()['next_cursor']}",
    )
    assert older.json()["items"]


def test_settings_target_and_strict_upload_validation(
    database_session_factory: object,
    app_client: object,
) -> None:
    csrf, device_token = _setup(app_client, database_session_factory)
    settings = app_client.request(  # type: ignore[union-attr]
        "PATCH",
        "/api/v1/settings",
        headers={"X-CSRF-Token": csrf},
        json={"attendance_target": "80"},
    )
    assert settings.status_code == 200
    assert settings.json()["attendance_target"] == 80

    malformed = app_client.request(  # type: ignore[union-attr]
        "POST",
        "/api/v1/connector/attendance",
        headers={"Authorization": f"Bearer {device_token}"},
        json={"subjects": [RECORDS[0], RECORDS[0]]},
    )
    assert malformed.status_code == 422
    unknown = app_client.request(  # type: ignore[union-attr]
        "POST",
        "/api/v1/connector/attendance",
        headers={"Authorization": f"Bearer {device_token}"},
        json={"subjects": [RECORDS[0] | {"html": "<table>"}]},
    )
    assert unknown.status_code == 422

    bearer_cannot_read = app_client.request(  # type: ignore[union-attr]
        "GET", "/api/v1/attendance", headers={"Authorization": f"Bearer {device_token}"}
    )
    app_client.cookies.clear()  # type: ignore[union-attr]
    bearer_cannot_read = app_client.request(  # type: ignore[union-attr]
        "GET", "/api/v1/attendance", headers={"Authorization": f"Bearer {device_token}"}
    )
    assert bearer_cannot_read.status_code == 401


def test_concurrent_duplicate_uploads_create_one_snapshot(
    database_session_factory: object,
) -> None:
    with database_session_factory() as session:  # type: ignore[operator]
        user = bootstrap_account(session, "owner@example.com", "a-very-long-password")
        device = ConnectorDevice(
            user_id=user.id,
            name="Chrome",
            token_hash=hash_opaque_token("device-token"),
        )
        session.add(device)
        session.commit()
        device_id = device.id

    batch = AttendanceUpload(subjects=[SubjectUpload(**RECORDS[0])])
    factory = database_session_factory

    def upload() -> int:
        with factory() as session:  # type: ignore[operator]
            return process_upload(session, device_id, batch).snapshots_created

    with ThreadPoolExecutor(max_workers=2) as executor:
        results = list(executor.map(lambda _: upload(), range(2)))
    assert sorted(results) == [0, 1]
    with factory() as session:  # type: ignore[operator]
        assert session.query(AttendanceSnapshot).count() == 1


def test_invalid_batch_rolls_back_without_writing(
    database_session_factory: object,
    app_client: object,
) -> None:
    _csrf, device_token = _setup(app_client, database_session_factory)
    headers = {"Authorization": f"Bearer {device_token}"}
    app_client.request(  # type: ignore[union-attr]
        "POST", "/api/v1/connector/attendance", headers=headers, json={"subjects": [RECORDS[0]]}
    )
    invalid = RECORDS[0] | {"attended_hours": 20}
    response = app_client.request(  # type: ignore[union-attr]
        "POST", "/api/v1/connector/attendance", headers=headers, json={"subjects": [invalid]}
    )
    assert response.status_code == 422
    assert app_client.request("GET", "/api/v1/attendance").json()["subjects"]  # type: ignore[union-attr]
