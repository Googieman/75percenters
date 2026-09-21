import base64
from datetime import timedelta

from srm_tracker.acquisition_provider import HostedSyncResult, ProviderChallenge, ProviderSession
from srm_tracker.admin import bootstrap_account
from srm_tracker.campusweb_provider import CAMPUSWEB_STUDENT_PORTAL
from srm_tracker.db_models import SrmConnection, Subject, SyncJob
from srm_tracker.schemas import AttendanceUpload, SubjectUpload
from srm_tracker.time import utc_now


def _login(client: object) -> str:
    response = client.request(  # type: ignore[union-attr]
        "POST",
        "/api/v1/auth/login",
        json={"email": "owner@example.com", "password": "a-very-long-password"},
    )
    assert response.status_code == 200
    return response.json()["csrf_token"]


class TestProvider:
    name = CAMPUSWEB_STUDENT_PORTAL

    def start_authentication(self, netid: str) -> ProviderChallenge:
        return ProviderChallenge("password", "Enter password", netid.encode())

    def complete_authentication(
        self, challenge: ProviderChallenge, password: str, response: str | None
    ) -> ProviderSession:
        assert password == "campus-password"
        del response
        return ProviderSession(challenge.state or b"", "AB1234", "2026-T1")

    def fetch_attendance(self, session: ProviderSession) -> HostedSyncResult:
        del session
        return HostedSyncResult(
            AttendanceUpload(
                subjects=[
                    SubjectUpload(
                        code="CSE1",
                        subject="Algorithms",
                        total_hours=1,
                        attended_hours=1,
                        absent_hours=0,
                        source_percentage="100",
                    )
                ]
            ),
            "2026-T1",
        )

    def disconnect(self, session: ProviderSession) -> None:
        del session


def _enable_provider(app_client: object) -> None:
    app_client.app.state.settings.acquisition_enabled = True  # type: ignore[union-attr]
    app_client.app.state.settings.session_encryption_key = base64.urlsafe_b64encode(  # type: ignore[union-attr]
        bytes(range(32))
    ).decode()
    app_client.app.state.acquisition_provider = TestProvider()  # type: ignore[union-attr]


def test_authentication_attempt_promotes_verified_identity_and_queues_first_refresh(
    database_session_factory: object,
    app_client: object,
) -> None:
    with database_session_factory() as session:  # type: ignore[operator]
        bootstrap_account(session, "owner@example.com", "a-very-long-password")
    _enable_provider(app_client)
    csrf = _login(app_client)

    started = app_client.request(  # type: ignore[union-attr]
        "POST",
        "/api/v1/srm/auth-attempts",
        headers={"X-CSRF-Token": csrf},
        json={"netid": "AB1234"},
    )
    assert started.status_code == 201
    attempt_id = started.json()["attempt_id"]

    completed = app_client.request(  # type: ignore[union-attr]
        "POST",
        f"/api/v1/srm/auth-attempts/{attempt_id}/complete",
        headers={"X-CSRF-Token": csrf},
        json={"password": "campus-password"},
    )
    assert completed.status_code == 200
    assert completed.json()["status"] == "succeeded"

    with database_session_factory() as session:  # type: ignore[operator]
        connection = session.query(SrmConnection).one()
        assert connection.provider == CAMPUSWEB_STUDENT_PORTAL
        assert connection.pending_netid is None
        assert connection.verified_netid == "AB1234"
        assert connection.encrypted_session_state is not None
        assert b"campus-password" not in connection.encrypted_session_state
        assert session.query(SyncJob).one().status == "queued"


def test_client_cannot_select_a_provider_for_authentication(
    database_session_factory: object,
    app_client: object,
) -> None:
    with database_session_factory() as session:  # type: ignore[operator]
        bootstrap_account(session, "owner@example.com", "a-very-long-password")
    _enable_provider(app_client)
    csrf = _login(app_client)

    response = app_client.request(  # type: ignore[union-attr]
        "POST",
        "/api/v1/srm/auth-attempts",
        headers={"X-CSRF-Token": csrf},
        json={"provider": "academia", "netid": "AB1234"},
    )

    assert response.status_code == 422


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
        json={"netid": "AB1234"},
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


def test_on_demand_sync_completes_without_a_background_worker(
    database_session_factory: object,
    app_client: object,
) -> None:
    with database_session_factory() as session:  # type: ignore[operator]
        bootstrap_account(session, "owner@example.com", "a-very-long-password")
    _enable_provider(app_client)
    app_client.app.state.settings.sync_execution_mode = "on_demand"  # type: ignore[union-attr]
    csrf = _login(app_client)

    started = app_client.request(  # type: ignore[union-attr]
        "POST",
        "/api/v1/srm/auth-attempts",
        headers={"X-CSRF-Token": csrf},
        json={"netid": "AB1234"},
    )
    assert started.status_code == 201
    completed = app_client.request(  # type: ignore[union-attr]
        "POST",
        f"/api/v1/srm/auth-attempts/{started.json()['attempt_id']}/complete",
        headers={"X-CSRF-Token": csrf},
        json={"password": "campus-password"},
    )
    assert completed.status_code == 200

    refreshed = app_client.request(  # type: ignore[union-attr]
        "POST", "/api/v1/srm/sync", headers={"X-CSRF-Token": csrf}
    )

    assert refreshed.status_code == 202
    assert refreshed.json()["status"] == "succeeded"
    with database_session_factory() as session:  # type: ignore[operator]
        assert session.query(SyncJob).one().status == "succeeded"
        assert session.query(Subject).one().code == "CSE1"


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
        "endpoint": "https://fcm.googleapis.com/fcm/send/subscription-1",
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
