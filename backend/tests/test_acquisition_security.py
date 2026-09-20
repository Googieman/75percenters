import base64

import pytest

from srm_tracker.acquisition_crypto import SessionCipher, SessionCipherError, SessionKeyring
from srm_tracker.db_models import AuthAttempt, SrmConnection, User
from srm_tracker.key_rotation import rotate_session_records
from srm_tracker.session_store import (
    decrypt_attempt_state,
    decrypt_session_state,
    store_attempt_state,
    store_session_state,
)


def test_session_cipher_round_trip_binds_state_to_owner_provider_and_generation() -> None:
    key = base64.urlsafe_b64encode(bytes(range(32))).decode("ascii")
    cipher = SessionCipher.from_base64(key, key_version=4)

    encrypted = cipher.encrypt(
        b"authenticated session", owner_id=9, provider="student_portal", generation=3
    )

    assert b"authenticated session" not in encrypted
    assert (
        cipher.decrypt(encrypted, owner_id=9, provider="student_portal", generation=3)
        == b"authenticated session"
    )
    with pytest.raises(SessionCipherError):
        cipher.decrypt(encrypted, owner_id=10, provider="student_portal", generation=3)
    with pytest.raises(SessionCipherError):
        cipher.decrypt(encrypted, owner_id=9, provider="student_portal", generation=4)


def test_session_cipher_rejects_invalid_key_material() -> None:
    with pytest.raises(SessionCipherError, match="32 bytes"):
        SessionCipher.from_base64(base64.urlsafe_b64encode(b"short").decode("ascii"))


def test_connection_session_state_is_encrypted_and_bound_before_storage() -> None:
    key = base64.urlsafe_b64encode(bytes(range(32))).decode("ascii")
    cipher = SessionCipher.from_base64(key, key_version=4)
    connection = SrmConnection(
        id=12,
        user_id=9,
        verified_netid="AB1234",
        provider="student_portal",
        generation=3,
    )

    store_session_state(connection, cipher, b"portal cookies")

    assert connection.encrypted_session_state is not None
    assert b"portal cookies" not in connection.encrypted_session_state
    assert connection.session_key_version == 4
    assert decrypt_session_state(connection, cipher) == b"portal cookies"


def test_auth_attempt_state_uses_the_same_authenticated_server_side_storage() -> None:
    key = base64.urlsafe_b64encode(bytes(range(32))).decode("ascii")
    cipher = SessionCipher.from_base64(key, key_version=4)
    attempt = AuthAttempt(
        id=15,
        user_id=9,
        provider="student_portal",
        connection_generation=3,
    )

    store_attempt_state(attempt, cipher, b"temporary challenge session")

    assert attempt.encrypted_state is not None
    assert b"temporary challenge session" not in attempt.encrypted_state
    assert decrypt_attempt_state(attempt, cipher) == b"temporary challenge session"


def test_keyring_reads_old_versions_and_reencrypts_with_active_key() -> None:
    old_key = base64.urlsafe_b64encode(bytes(range(32))).decode("ascii")
    new_key = base64.urlsafe_b64encode(bytes(reversed(range(32)))).decode("ascii")
    keyring = SessionKeyring.from_base64(
        {1: old_key, 2: new_key},
        active_version=2,
    )
    old_ciphertext = keyring.cipher(1).encrypt(
        b"rotating state", owner_id=9, provider="campusweb_student_portal", generation=3
    )

    rotated = keyring.rotate(
        old_ciphertext,
        old_version=1,
        owner_id=9,
        provider="campusweb_student_portal",
        generation=3,
    )

    assert keyring.decrypt(
        rotated,
        version=2,
        owner_id=9,
        provider="campusweb_student_portal",
        generation=3,
    ) == b"rotating state"
    assert rotated != old_ciphertext


def test_resumable_rotation_preserves_connection_generation(
    database_session_factory: object,
) -> None:
    old_key = base64.urlsafe_b64encode(bytes(range(32))).decode("ascii")
    new_key = base64.urlsafe_b64encode(bytes(reversed(range(32)))).decode("ascii")
    keyring = SessionKeyring.from_base64({1: old_key, 2: new_key}, active_version=2)
    with database_session_factory() as session:  # type: ignore[operator]
        session.add(User(id=9, email="rotation@example.com", password_hash="test-hash"))
        connection = SrmConnection(
            id=12,
            user_id=9,
            verified_netid="AB1234",
            provider="campusweb_student_portal",
            generation=7,
            session_key_version=1,
            encrypted_session_state=keyring.cipher(1).encrypt(
                b"connection state",
                owner_id=9,
                provider="campusweb_student_portal",
                generation=7,
            ),
        )
        session.add(connection)
        session.commit()

    assert rotate_session_records(database_session_factory, keyring) == 1  # type: ignore[arg-type]
    with database_session_factory() as session:  # type: ignore[operator]
        connection = session.get(SrmConnection, 12)
        assert connection is not None
        assert connection.generation == 7
        assert connection.session_key_version == 2
        assert decrypt_session_state(connection, keyring) == b"connection state"
