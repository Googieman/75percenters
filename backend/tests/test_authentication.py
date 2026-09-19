from datetime import timedelta

from srm_tracker.admin import bootstrap_account
from srm_tracker.db_models import Session as AuthSession
from srm_tracker.security import hash_opaque_token
from srm_tracker.time import utc_now


def test_login_me_logout_and_csrf_protect_browser_writes(
    database_session_factory: object,
    app_client: object,
) -> None:
    with database_session_factory() as session:  # type: ignore[operator]
        bootstrap_account(session, "owner@example.com", "a-very-long-password")

    client = app_client
    response = client.request(  # type: ignore[union-attr]
        "POST",
        "/api/v1/auth/login",
        json={"email": "OWNER@example.com", "password": "a-very-long-password"},
    )
    assert response.status_code == 200
    body = response.json()
    assert body["user"]["email"] == "owner@example.com"
    assert body["csrf_token"]
    assert "srm_tracker_session" not in body
    assert any(
        "HttpOnly" in value and "SameSite=lax" in value
        for value in response.headers.get_list("set-cookie")
    )

    me = client.request("GET", "/api/v1/auth/me")  # type: ignore[union-attr]
    assert me.status_code == 200
    assert me.json()["csrf_token"] == body["csrf_token"]

    without_csrf = client.request("POST", "/api/v1/auth/logout")  # type: ignore[union-attr]
    assert without_csrf.status_code == 403
    logout = client.request(  # type: ignore[union-attr]
        "POST", "/api/v1/auth/logout", headers={"X-CSRF-Token": body["csrf_token"]}
    )
    assert logout.status_code == 204
    assert client.request("GET", "/api/v1/auth/me").status_code == 401  # type: ignore[union-attr]


def test_expired_session_is_rejected(
    database_session_factory: object,
    app_client: object,
) -> None:
    with database_session_factory() as session:  # type: ignore[operator]
        user = bootstrap_account(session, "owner@example.com", "a-very-long-password")
        token = "expired-token"
        session.add(
            AuthSession(
                user_id=user.id,
                token_hash=hash_opaque_token(token),
                csrf_token_hash=hash_opaque_token("csrf-token"),
                expires_at=utc_now() - timedelta(seconds=1),
            )
        )
        session.commit()

    client = app_client
    client.cookies["srm_tracker_session"] = token  # type: ignore[union-attr]
    assert client.request("GET", "/api/v1/auth/me").status_code == 401  # type: ignore[union-attr]


def test_login_rate_limit_returns_retry_after(
    database_session_factory: object,
    app_client: object,
) -> None:
    with database_session_factory() as session:  # type: ignore[operator]
        bootstrap_account(session, "owner@example.com", "a-very-long-password")

    client = app_client
    for _ in range(5):
        response = client.request(  # type: ignore[union-attr]
            "POST",
            "/api/v1/auth/login",
            json={"email": "owner@example.com", "password": "wrong-password"},
        )
        assert response.status_code == 401
    limited = client.request(  # type: ignore[union-attr]
        "POST",
        "/api/v1/auth/login",
        json={"email": "owner@example.com", "password": "wrong-password"},
    )
    assert limited.status_code == 429
    assert int(limited.headers["retry-after"]) > 0


def test_cors_allows_only_configured_origin(app_client: object) -> None:
    response = app_client.request(  # type: ignore[union-attr]
        "OPTIONS",
        "/api/v1/auth/me",
        headers={
            "Origin": "http://localhost:5173",
            "Access-Control-Request-Method": "GET",
        },
    )
    assert response.status_code == 200
    assert response.headers["access-control-allow-origin"] == "http://localhost:5173"

    foreign = app_client.request(  # type: ignore[union-attr]
        "OPTIONS",
        "/api/v1/auth/me",
        headers={
            "Origin": "https://foreign.example",
            "Access-Control-Request-Method": "GET",
        },
    )
    assert "access-control-allow-origin" not in foreign.headers
