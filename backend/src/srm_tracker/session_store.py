"""Encrypted storage helpers for provider session state."""

from srm_tracker.acquisition_crypto import SessionCipher, SessionCipherError, SessionKeyring
from srm_tracker.db_models import AuthAttempt, SrmConnection

CipherStore = SessionCipher | SessionKeyring


def store_session_state(connection: SrmConnection, cipher: CipherStore, state: bytes) -> None:
    if connection.id <= 0 or connection.user_id <= 0:
        raise SessionCipherError("connection must be persisted before storing state")
    connection.encrypted_session_state = cipher.encrypt(
        state,
        owner_id=connection.user_id,
        provider=connection.provider,
        generation=connection.generation,
    )
    connection.session_key_version = cipher.key_version


def decrypt_session_state(connection: SrmConnection, cipher: CipherStore) -> bytes:
    encrypted = connection.encrypted_session_state
    if encrypted is None:
        raise SessionCipherError("SRM connection has no active session state")
    if isinstance(cipher, SessionKeyring):
        return cipher.decrypt(
            encrypted,
            version=connection.session_key_version,
            owner_id=connection.user_id,
            provider=connection.provider,
            generation=connection.generation,
        )
    if connection.session_key_version != cipher.key_version:
        raise SessionCipherError("session encryption key version is not available")
    return cipher.decrypt(
        encrypted,
        owner_id=connection.user_id,
        provider=connection.provider,
        generation=connection.generation,
    )


def store_attempt_state(attempt: AuthAttempt, cipher: CipherStore, state: bytes) -> None:
    if attempt.id <= 0 or attempt.user_id <= 0:
        raise SessionCipherError("authentication attempt must be persisted before storing state")
    attempt.encrypted_state = cipher.encrypt(
        state,
        owner_id=attempt.user_id,
        provider=attempt.provider,
        generation=attempt.connection_generation,
        binding_id=attempt.id,
    )
    attempt.state_key_version = cipher.key_version


def decrypt_attempt_state(attempt: AuthAttempt, cipher: CipherStore) -> bytes:
    encrypted = attempt.encrypted_state
    if encrypted is None or attempt.state_key_version is None:
        raise SessionCipherError("authentication attempt state is unavailable")
    if isinstance(cipher, SessionKeyring):
        return cipher.decrypt(
            encrypted,
            version=attempt.state_key_version,
            owner_id=attempt.user_id,
            provider=attempt.provider,
            generation=attempt.connection_generation,
            binding_id=attempt.id,
        )
    if attempt.state_key_version != cipher.key_version:
        raise SessionCipherError("session encryption key version is not available")
    return cipher.decrypt(
        encrypted,
        owner_id=attempt.user_id,
        provider=attempt.provider,
        generation=attempt.connection_generation,
        binding_id=attempt.id,
    )
