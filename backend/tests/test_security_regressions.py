from decimal import Decimal

from srm_tracker.admin import bootstrap_account
from srm_tracker.config import Settings
from srm_tracker.db_models import Subject, User
from srm_tracker.main import create_app
from srm_tracker.security import hash_password


def _login(client: object) -> str:
    response = client.request(  # type: ignore[union-attr]
        "POST",
        "/api/v1/auth/login",
        _base_url="https://testserver",
        json={"email": "owner@example.com", "password": "a-very-long-password"},
    )
    assert response.status_code == 200
    return response.json()["csrf_token"]


def test_production_login_sets_secure_http_only_session_cookie(
    database_session_factory: object,
    app_client: object,
) -> None:
    with database_session_factory() as session:  # type: ignore[operator]
        bootstrap_account(session, "owner@example.com", "a-very-long-password")

    production_settings = Settings(
        environment="production",
        database_url="postgresql+psycopg://srm_tracker:srm_tracker@localhost:55432/srm_tracker_test",
        frontend_origin="https://dashboard.example",
        session_encryption_key="AAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAA=",
    )
    app_client.app = create_app(  # type: ignore[union-attr]
        settings=production_settings,
        session_factory=database_session_factory,
    )
    response = app_client.request(  # type: ignore[union-attr]
        "POST",
        "/api/v1/auth/login",
        _base_url="https://testserver",
        json={"email": "owner@example.com", "password": "a-very-long-password"},
    )
    cookies = response.headers.get_list("set-cookie")
    assert any("Secure" in cookie and "HttpOnly" in cookie for cookie in cookies)


def test_staging_login_sets_secure_session_and_csrf_cookies(
    database_session_factory: object,
    app_client: object,
) -> None:
    with database_session_factory() as session:  # type: ignore[operator]
        bootstrap_account(session, "owner@example.com", "a-very-long-password")

    staging_settings = Settings(
        environment="staging",
        database_url="postgresql+psycopg://srm_tracker:srm_tracker@localhost:55432/srm_tracker_test",
        frontend_origin="https://dashboard.example",
        session_encryption_key="AAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAA=",
    )
    app_client.app = create_app(  # type: ignore[union-attr]
        settings=staging_settings,
        session_factory=database_session_factory,
    )
    response = app_client.request(  # type: ignore[union-attr]
        "POST",
        "/api/v1/auth/login",
        _base_url="https://testserver",
        json={"email": "owner@example.com", "password": "a-very-long-password"},
    )

    cookies = response.headers.get_list("set-cookie")
    assert len(cookies) == 2
    assert all("Secure" in cookie for cookie in cookies)


def test_production_redirects_http_requests_to_https(
    database_session_factory: object,
    app_client: object,
) -> None:
    with database_session_factory() as session:  # type: ignore[operator]
        bootstrap_account(session, "owner@example.com", "a-very-long-password")
    production_settings = Settings(
        environment="production",
        database_url="postgresql+psycopg://srm_tracker:srm_tracker@localhost:55432/srm_tracker_test",
        frontend_origin="https://dashboard.example",
        session_encryption_key="AAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAA=",
    )
    app_client.app = create_app(  # type: ignore[union-attr]
        settings=production_settings,
        session_factory=database_session_factory,
    )
    response = app_client.request(  # type: ignore[union-attr]
        "GET", "/api/v1/health", _base_url="http://testserver"
    )
    assert response.status_code == 307
    assert response.headers["location"] == "https://testserver/api/v1/health"


def test_browser_session_cannot_ingest_and_connector_cannot_manage_settings(
    database_session_factory: object,
    app_client: object,
) -> None:
    with database_session_factory() as session:  # type: ignore[operator]
        bootstrap_account(session, "owner@example.com", "a-very-long-password")
    csrf = _login(app_client)
    browser_upload = app_client.request(  # type: ignore[union-attr]
        "POST", "/api/v1/connector/attendance", json={"subjects": []}
    )
    assert browser_upload.status_code == 401

    code = app_client.request(  # type: ignore[union-attr]
        "POST", "/api/v1/pairing-codes", headers={"X-CSRF-Token": csrf}
    ).json()["code"]
    paired = app_client.request(  # type: ignore[union-attr]
        "POST", "/api/v1/connector/pair", json={"code": code}
    ).json()
    app_client.cookies.clear()  # type: ignore[union-attr]
    connector_settings = app_client.request(  # type: ignore[union-attr]
        "PATCH",
        "/api/v1/settings",
        headers={"Authorization": f"Bearer {paired['device_token']}"},
        json={"attendance_target": "80"},
    )
    assert connector_settings.status_code == 401


def test_foreign_subject_history_returns_not_found(
    database_session_factory: object,
    app_client: object,
) -> None:
    with database_session_factory() as session:  # type: ignore[operator]
        owner = bootstrap_account(session, "owner@example.com", "a-very-long-password")
        other = User(email="other@example.com", password_hash=hash_password("a-different-password"))
        session.add(other)
        session.flush()
        subject = Subject(
            user_id=other.id,
            code="OTHER1",
            name="Other",
            total_hours=1,
            attended_hours=1,
            absent_hours=0,
            source_percentage=Decimal("100"),
        )
        session.add(subject)
        session.commit()
        foreign_subject_id = subject.id
        assert owner.id != other.id

    _login(app_client)
    response = app_client.request(  # type: ignore[union-attr]
        "GET", f"/api/v1/subjects/{foreign_subject_id}/history"
    )
    assert response.status_code == 404
