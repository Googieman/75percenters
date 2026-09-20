from datetime import timedelta

from srm_tracker.acquisition_service import queue_reauthentication_notice
from srm_tracker.admin import bootstrap_account
from srm_tracker.db_models import NotificationDelivery, PushSubscription
from srm_tracker.notification_dispatcher import (
    NotificationDispatcher,
    PushSendResult,
)
from srm_tracker.time import utc_now


class FakeTransport:
    def __init__(self, responses: list[PushSendResult]) -> None:
        self.responses = responses
        self.payloads: list[str] = []

    def send(self, subscription: PushSubscription, payload: str) -> PushSendResult:
        self.payloads.append(payload)
        return self.responses.pop(0)


def _seed_notice(database_session_factory: object) -> tuple[int, int]:
    with database_session_factory() as session:  # type: ignore[operator]
        user = bootstrap_account(session, "notice@example.com", "a-very-long-password")
        session.add(
            PushSubscription(
                user_id=user.id,
                endpoint="https://fcm.googleapis.com/fcm/send/notice-1",
                p256dh="public-key",
                auth="auth-secret",
            )
        )
        session.commit()
        notice = queue_reauthentication_notice(session, user.id, generation=4)
        return notice.id, user.id


def test_notification_dispatch_tracks_each_subscription_and_sends_safe_payload(
    database_session_factory: object,
) -> None:
    notice_id, _user_id = _seed_notice(database_session_factory)
    transport = FakeTransport([PushSendResult(status_code=201)])
    dispatcher = NotificationDispatcher(database_session_factory, transport)

    assert dispatcher.run_once() == 1
    assert len(transport.payloads) == 1
    assert "user_id" not in transport.payloads[0]
    assert "notice@example.com" not in transport.payloads[0]
    assert "srm-reauthentication" in transport.payloads[0]

    with database_session_factory() as session:  # type: ignore[operator]
        delivery = session.query(NotificationDelivery).filter_by(notification_id=notice_id).one()
        assert delivery.status == "delivered"
        assert dispatcher.run_once() == 0


def test_notification_dispatch_removes_gone_subscription(
    database_session_factory: object,
) -> None:
    _seed_notice(database_session_factory)
    transport = FakeTransport([PushSendResult(status_code=410)])
    dispatcher = NotificationDispatcher(database_session_factory, transport)

    assert dispatcher.run_once() == 1
    with database_session_factory() as session:  # type: ignore[operator]
        assert session.query(PushSubscription).count() == 0


def test_notification_dispatch_retries_temporary_delivery_failure(
    database_session_factory: object,
) -> None:
    notice_id, _user_id = _seed_notice(database_session_factory)
    transport = FakeTransport([PushSendResult(status_code=429, retry_after=120)])
    dispatcher = NotificationDispatcher(database_session_factory, transport)

    assert dispatcher.run_once() == 1
    with database_session_factory() as session:  # type: ignore[operator]
        delivery = session.query(NotificationDelivery).filter_by(notification_id=notice_id).one()
        assert delivery.status == "pending"
        assert delivery.available_at >= utc_now() + timedelta(seconds=119)
