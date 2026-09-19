from srm_tracker.admin import bootstrap_account

RECORD = {
    "code": "CSE1",
    "subject": "Algorithms",
    "total_hours": 23,
    "attended_hours": 16,
    "absent_hours": 7,
    "source_percentage": "69.57",
}


def test_bootstrap_login_pair_upload_history_revoke_flow(
    database_session_factory: object,
    app_client: object,
) -> None:
    with database_session_factory() as session:  # type: ignore[operator]
        bootstrap_account(session, "owner@example.com", "a-very-long-password")

    client = app_client
    login = client.request(  # type: ignore[union-attr]
        "POST",
        "/api/v1/auth/login",
        json={"email": "owner@example.com", "password": "a-very-long-password"},
    )
    csrf = login.json()["csrf_token"]
    code = client.request(  # type: ignore[union-attr]
        "POST", "/api/v1/pairing-codes", headers={"X-CSRF-Token": csrf}
    ).json()["code"]
    paired = client.request(  # type: ignore[union-attr]
        "POST", "/api/v1/connector/pair", json={"code": code}
    ).json()
    token = paired["device_token"]

    uploaded = client.request(  # type: ignore[union-attr]
        "POST",
        "/api/v1/connector/attendance",
        headers={"Authorization": f"Bearer {token}"},
        json={"subjects": [RECORD]},
    )
    assert uploaded.status_code == 200
    attendance = client.request("GET", "/api/v1/attendance")  # type: ignore[union-attr]
    subject_id = attendance.json()["subjects"][0]["id"]
    history = client.request(  # type: ignore[union-attr]
        "GET", f"/api/v1/subjects/{subject_id}/history"
    )
    assert history.status_code == 200
    assert history.json()["items"][0]["attended_hours"] == 16

    revoked = client.request(  # type: ignore[union-attr]
        "DELETE",
        f"/api/v1/devices/{paired['device_id']}",
        headers={"X-CSRF-Token": csrf},
    )
    assert revoked.status_code == 204
    client.cookies.clear()  # type: ignore[union-attr]
    rejected = client.request(  # type: ignore[union-attr]
        "POST",
        "/api/v1/connector/attendance",
        headers={"Authorization": f"Bearer {token}"},
        json={"subjects": [RECORD]},
    )
    assert rejected.status_code == 401
