"""Resumable server-side session key rotation."""

from sqlalchemy import select
from sqlalchemy.orm import Session as DbSession
from sqlalchemy.orm import sessionmaker

from srm_tracker.acquisition_crypto import SessionCipherError, SessionKeyring
from srm_tracker.db_models import AuthAttempt, SrmConnection


def validate_keyring_usage(session: DbSession, keyring: SessionKeyring) -> None:
    """Refuse startup when an active record depends on a retired read key."""
    versions = set(
        session.scalars(
            select(SrmConnection.session_key_version).where(
                SrmConnection.encrypted_session_state.is_not(None)
            )
        )
    )
    versions.update(
        version
        for version in session.scalars(
            select(AuthAttempt.state_key_version).where(AuthAttempt.encrypted_state.is_not(None))
        )
        if version is not None
    )
    unavailable = versions.difference(keyring.readable_versions)
    if unavailable:
        raise SessionCipherError("a retained session record requires a missing encryption key")


def rotate_session_records(
    session_factory: sessionmaker[DbSession],
    keyring: SessionKeyring,
    *,
    batch_size: int = 100,
) -> int:
    """Rotate a bounded batch per transaction; rerun until the return value is zero."""
    if batch_size <= 0:
        raise ValueError("batch_size must be positive")
    rotated = 0
    with session_factory() as session:
        validate_keyring_usage(session, keyring)
        connections = session.scalars(
            select(SrmConnection)
            .where(
                SrmConnection.encrypted_session_state.is_not(None),
                SrmConnection.session_key_version != keyring.active_version,
            )
            .order_by(SrmConnection.id)
            .limit(batch_size)
            .with_for_update()
        ).all()
        attempts = session.scalars(
            select(AuthAttempt)
            .where(
                AuthAttempt.encrypted_state.is_not(None),
                AuthAttempt.state_key_version != keyring.active_version,
            )
            .order_by(AuthAttempt.id)
            .limit(max(0, batch_size - len(connections)))
            .with_for_update()
        ).all()
        for connection in connections:
            assert connection.encrypted_session_state is not None
            connection.encrypted_session_state = keyring.rotate(
                connection.encrypted_session_state,
                old_version=connection.session_key_version,
                owner_id=connection.user_id,
                provider=connection.provider,
                generation=connection.generation,
            )
            connection.session_key_version = keyring.active_version
            rotated += 1
        for attempt in attempts:
            assert attempt.encrypted_state is not None
            assert attempt.state_key_version is not None
            attempt.encrypted_state = keyring.rotate(
                attempt.encrypted_state,
                old_version=attempt.state_key_version,
                owner_id=attempt.user_id,
                provider=attempt.provider,
                generation=attempt.connection_generation,
                binding_id=attempt.id,
            )
            attempt.state_key_version = keyring.active_version
            rotated += 1
        session.commit()
    return rotated
