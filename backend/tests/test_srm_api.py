from datetime import timedelta

from srm_tracker.admin import bootstrap_account
from srm_tracker.db_models import SrmConnection, SyncJob
from srm_tracker.time import utc_now


def _login(client: object) -> str:
    response = client.request(  # type: ignore[union-attr]
        "POST",
        "/api/v1/auth/login",
        json={"email": "owner@example.com", "password": "a-very-long-password"},
    )
    assert response.status_code == 200
    return response.json()["csrf_token"]


def test_connection_status_is_safe_and_source_independent(
    database_session_factory: object,
    app_client: object,
) -> None:
    with database_session_factory() as session:  # type: ignore[operator]
        bootstrap_account(session, "owner@example.com", "a-very-long-password")
    _login(app_client)

    response = app_client.request("GET", "/api/v1/srm/connection")  # type: ignore[union-attr]

    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "disconnected"
    assert body["last_successful_sync"] is None
    assert "encrypted_session_state" not in body
    assert "password" not in body


def test_authentication_attempts_are_feature_gated_before_accepting_credentials(
    database_session_factory: object,
    app_client: object,
) -> None:
    with database_session_factory() as session:  # type: ignore[operator]
        bootstrap_account(session, "owner@example.com", "a-very-long-password")
    csrf = _login(app_client)

    response = app_client.request(  # type: ignore[union-attr]
        "POST",
        "/api/v1/srm/auth-attempts",
        headers={"X-CSRF-Token": csrf},
        json={"provider": "student_portal", "netid": "AB1234"},
    )

    assert response.status_code == 503
    assert "verification" in response.json()["detail"].lower()


def test_manual_sync_is_queued_and_coalesced_for_connected_account(
    database_session_factory: object,
    app_client: object,
) -> None:
    with database_session_factory() as session:  # type: ignore[operator]
        user = bootstrap_account(session, "owner@example.com", "a-very-long-password")
        session.add(
            SrmConnection(
                user_id=user.id,
                verified_netid="AB1234",
                provider="student_portal",
                status="connected",
                generation=2,
                encrypted_session_state=b"opaque",
            )
        )
        session.commit()
    app_client.app.state.settings.acquisition_enabled = True  # type: ignore[union-attr]
    csrf = _login(app_client)

    first = app_client.request(  # type: ignore[union-attr]
        "POST", "/api/v1/srm/sync", headers={"X-CSRF-Token": csrf}
    )
    second = app_client.request(  # type: ignore[union-attr]
        "POST", "/api/v1/srm/sync", headers={"X-CSRF-Token": csrf}
    )

    assert first.status_code == 202
    assert second.status_code == 202
    assert first.json()["job_id"] == second.json()["job_id"]
    job = app_client.request(  # type: ignore[union-attr]
        "GET", f"/api/v1/srm/sync-jobs/{first.json()['job_id']}"
    )
    assert job.status_code == 200
    assert job.json()["status"] == "queued"


def test_disconnect_cancels_jobs_and_removes_active_session_material(
    database_session_factory: object,
    app_client: object,
) -> None:
    with database_session_factory() as session:  # type: ignore[operator]
        user = bootstrap_account(session, "owner@example.com", "a-very-long-password")
        connection = SrmConnection(
            user_id=user.id,
            verified_netid="AB1234",
            provider="student_portal",
            status="connected",
            generation=4,
            encrypted_session_state=b"opaque",
        )
        session.add(connection)
        session.flush()
        session.add(
            SyncJob(
                user_id=user.id,
                connection_id=connection.id,
                source_provider="student_portal",
                status="queued",
                scheduled_for=utc_now() + timedelta(minutes=1),
                connection_generation=4,
            )
        )
        session.commit()
    csrf = _login(app_client)

    response = app_client.request(  # type: ignore[union-attr]
        "DELETE", "/api/v1/srm/connection", headers={"X-CSRF-Token": csrf}
    )

    assert response.status_code == 204
    with database_session_factory() as session:  # type: ignore[operator]
        saved = session.query(SrmConnection).one()
        assert saved.status == "disconnected"
        assert saved.encrypted_session_state is None
        assert saved.generation == 5
        assert session.query(SyncJob).one().status == "canceled"


def test_push_subscription_can_be_replaced_and_removed(
    database_session_factory: object,
    app_client: object,
) -> None:
    with database_session_factory() as session:  # type: ignore[operator]
        bootstrap_account(session, "owner@example.com", "a-very-long-password")
    csrf = _login(app_client)
    payload = {
        "endpoint": "https://push.example/subscription/1",
        "keys": {"p256dh": "public-key", "auth": "auth-secret"},
    }

    first = app_client.request(  # type: ignore[union-attr]
        "POST", "/api/v1/push-subscriptions", headers={"X-CSRF-Token": csrf}, json=payload
    )
    second = app_client.request(  # type: ignore[union-attr]
        "POST", "/api/v1/push-subscriptions", headers={"X-CSRF-Token": csrf}, json=payload
    )

    assert first.status_code == 200
    assert second.status_code == 200
    assert first.json()["subscription_id"] == second.json()["subscription_id"]
    deleted = app_client.request(  # type: ignore[union-attr]
        "DELETE",
        f"/api/v1/push-subscriptions/{first.json()['subscription_id']}",
        headers={"X-CSRF-Token": csrf},
    )
    assert deleted.status_code == 204
