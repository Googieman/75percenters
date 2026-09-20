"""Render-friendly background worker entrypoint."""

import logging
from threading import Event

from srm_tracker.acquisition_crypto import SessionCipherError, SessionKeyring, keyring_from_settings
from srm_tracker.campusweb_provider import CampusWebProvider
from srm_tracker.campusweb_worker import CampusWebSyncExecutor
from srm_tracker.config import Settings, get_settings
from srm_tracker.db import create_engine_from_settings, session_factory_for_engine
from srm_tracker.key_rotation import validate_keyring_usage
from srm_tracker.notification_dispatcher import NotificationDispatcher, PyWebPushTransport
from srm_tracker.worker import SyncWorker

LOGGER = logging.getLogger("srm_tracker.worker")


def build_keyring(settings: Settings) -> SessionKeyring:
    if not settings.session_encryption_key:
        raise SessionCipherError("worker session encryption is not configured")
    return keyring_from_settings(
        settings.session_encryption_key,
        active_version=settings.session_encryption_key_version,
        read_keys_json=settings.session_encryption_read_keys,
    )


def run_worker(settings: Settings | None = None, stop_event: Event | None = None) -> None:
    settings = settings or get_settings()
    stop_event = stop_event or Event()
    engine = create_engine_from_settings(settings)
    session_factory = session_factory_for_engine(engine)
    keyring = build_keyring(settings)
    with session_factory() as session:
        validate_keyring_usage(session, keyring)
    provider = CampusWebProvider()
    worker = SyncWorker(
        session_factory,
        CampusWebSyncExecutor(session_factory, provider, keyring),
        poll_interval_seconds=settings.sync_poll_interval_seconds,
        scheduled_interval_minutes=settings.sync_hourly_interval_minutes,
        cipher=keyring,
    )
    dispatcher = None
    if (
        settings.web_push_public_key
        and settings.web_push_private_key
        and settings.web_push_subject
    ):
        dispatcher = NotificationDispatcher(
            session_factory,
            PyWebPushTransport(
                private_key=settings.web_push_private_key,
                subject=settings.web_push_subject,
            ),
        )

    try:
        while not stop_event.is_set():
            try:
                if settings.acquisition_enabled:
                    worker.run_once()
                if dispatcher is not None:
                    dispatcher.run_once()
            except Exception:
                LOGGER.error("worker iteration failed; retrying on the next poll")
            stop_event.wait(settings.sync_poll_interval_seconds)
    finally:
        engine.dispose()


def main() -> None:
    run_worker()


if __name__ == "__main__":  # pragma: no cover
    main()
