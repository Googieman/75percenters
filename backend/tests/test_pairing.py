from concurrent.futures import ThreadPoolExecutor
from datetime import timedelta

from srm_tracker.admin import bootstrap_account
from srm_tracker.db_models import PairingCode, User
from srm_tracker.pairing import exchange_pairing_code
from srm_tracker.security import hash_opaque_token
from srm_tracker.time import utc_now


def _login(client: object, email: str = "owner@example.com") -> str:
    response = client.request(  # type: ignore[union-attr]
        "POST",
        "/api/v1/auth/login",
        json={"email": email, "password": "a-very-long-password"},
    )
    assert response.status_code == 200
    return response.json()["csrf_token"]


def test_pairing_code_is_one_use_and_device_token_is_returned_once(
    database_session_factory: object,
    app_client: object,
) -> None:
    with database_session_factory() as session:  # type: ignore[operator]
        bootstrap_account(session, "owner@example.com", "a-very-long-password")

    client = app_client
    csrf = _login(client)
    without_csrf = client.request("POST", "/api/v1/pairing-codes")  # type: ignore[union-attr]
    assert without_csrf.status_code == 403
    created = client.request(  # type: ignore[union-attr]
        "POST", "/api/v1/pairing-codes", headers={"X-CSRF-Token": csrf}
    )
    assert created.status_code == 200
    code = created.json()["code"]
    assert code

    paired = client.request(  # type: ignore[union-attr]
        "POST", "/api/v1/connector/pair", json={"code": code, "name": "Chrome"}
    )
    assert paired.status_code == 200
    body = paired.json()
    assert body["device_token"]
    assert "token_hash" not in body

    devices = client.request("GET", "/api/v1/devices")  # type: ignore[union-attr]
    assert devices.status_code == 200
    assert devices.json()[0]["name"] == "Chrome"
    assert "device_token" not in devices.json()[0]

    reused = client.request(  # type: ignore[union-attr]
        "POST", "/api/v1/connector/pair", json={"code": code, "name": "Second"}
    )
    assert reused.status_code == 400


def test_expired_pairing_code_and_rate_limit_are_rejected(
    database_session_factory: object,
    app_client: object,
) -> None:
    with database_session_factory() as session:  # type: ignore[operator]
        user = bootstrap_account(session, "owner@example.com", "a-very-long-password")
        code = PairingCode(
            user_id=user.id,
            code_hash=hash_opaque_token("expired-code"),
            expires_at=utc_now() - timedelta(seconds=1),
        )
        session.add(code)
        session.commit()

    client = app_client
    assert client.request(  # type: ignore[union-attr]
        "POST", "/api/v1/connector/pair", json={"code": "expired-code"}
    ).status_code == 400
    for _ in range(9):
        assert client.request(  # type: ignore[union-attr]
            "POST", "/api/v1/connector/pair", json={"code": "not-a-code"}
        ).status_code == 400
    limited = client.request(  # type: ignore[union-attr]
        "POST", "/api/v1/connector/pair", json={"code": "not-a-code"}
    )
    assert limited.status_code == 429
    assert int(limited.headers["retry-after"]) > 0


def test_concurrent_exchange_consumes_code_once(database_session_factory: object) -> None:
    with database_session_factory() as session:  # type: ignore[operator]
        user = bootstrap_account(session, "owner@example.com", "a-very-long-password")
        code = "concurrent-code"
        session.add(
            PairingCode(
                user_id=user.id,
                code_hash=hash_opaque_token(code),
                expires_at=utc_now() + timedelta(minutes=10),
            )
        )
        session.commit()

    factory = database_session_factory

    def exchange() -> bool:
        with factory() as session:  # type: ignore[operator]
            try:
                exchange_pairing_code(session, code, "Chrome")
                return True
            except ValueError:
                return False

    with ThreadPoolExecutor(max_workers=2) as executor:
        results = list(executor.map(lambda _: exchange(), range(2)))
    assert sorted(results) == [False, True]


def test_foreign_device_id_is_not_disclosed(
    database_session_factory: object,
    app_client: object,
) -> None:
    with database_session_factory() as session:  # type: ignore[operator]
        bootstrap_account(session, "owner@example.com", "a-very-long-password")
        session.add(
            User(email="other@example.com", password_hash="not-used-for-this-test")
        )
        session.commit()

    client = app_client
    csrf = _login(client)
    created = client.request(  # type: ignore[union-attr]
        "POST", "/api/v1/pairing-codes", headers={"X-CSRF-Token": csrf}
    )
    code = created.json()["code"]
    paired = client.request(  # type: ignore[union-attr]
        "POST", "/api/v1/connector/pair", json={"code": code}
    )
    device_id = paired.json()["device_id"]
    assert client.request(  # type: ignore[union-attr]
        "DELETE", f"/api/v1/devices/{device_id + 1}", headers={"X-CSRF-Token": csrf}
    ).status_code == 404


def test_revocation_is_immediate(
    database_session_factory: object,
    app_client: object,
) -> None:
    with database_session_factory() as session:  # type: ignore[operator]
        bootstrap_account(session, "owner@example.com", "a-very-long-password")

    client = app_client
    csrf = _login(client)
    code = client.request(  # type: ignore[union-attr]
        "POST", "/api/v1/pairing-codes", headers={"X-CSRF-Token": csrf}
    ).json()["code"]
    paired = client.request(  # type: ignore[union-attr]
        "POST", "/api/v1/connector/pair", json={"code": code}
    ).json()
    revoked = client.request(  # type: ignore[union-attr]
        "DELETE",
        f"/api/v1/devices/{paired['device_id']}",
        headers={"X-CSRF-Token": csrf},
    )
    assert revoked.status_code == 204
    client.cookies.clear()  # type: ignore[union-attr]
    assert client.request(  # type: ignore[union-attr]
        "GET", "/api/v1/devices", headers={"Authorization": f"Bearer {paired['device_token']}"}
    ).status_code == 401
