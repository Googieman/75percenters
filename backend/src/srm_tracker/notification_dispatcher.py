"""Durable, data-free Web Push delivery for reauthentication episodes."""

import json
from contextlib import suppress
from dataclasses import dataclass
from datetime import timedelta
from typing import Protocol

from sqlalchemy import select
from sqlalchemy.orm import Session as DbSession
from sqlalchemy.orm import sessionmaker

from srm_tracker.db_models import NotificationDelivery, NotificationOutbox, PushSubscription
from srm_tracker.time import utc_now


@dataclass(frozen=True, slots=True)
class PushSendResult:
    status_code: int
    retry_after: int | None = None


class PushTransport(Protocol):
    def send(self, subscription: PushSubscription, payload: str) -> PushSendResult:
        """Send one payload without logging subscription material or response bodies."""


class PyWebPushTransport:
    """VAPID transport kept behind a small injectable boundary for tests."""

    def __init__(self, *, private_key: str, subject: str) -> None:
        try:
            from pywebpush import webpush  # type: ignore[import-untyped]
        except ImportError as error:  # pragma: no cover - exercised by deployment smoke checks
            raise RuntimeError("pywebpush is required for notification delivery") from error
        self._webpush = webpush
        self._private_key = private_key
        self._subject = subject

    def send(self, subscription: PushSubscription, payload: str) -> PushSendResult:
        try:
            response = self._webpush(
                subscription_info={
                    "endpoint": subscription.endpoint,
                    "keys": {"p256dh": subscription.p256dh, "auth": subscription.auth},
                },
                data=payload,
                vapid_private_key=self._private_key,
                vapid_claims={"sub": self._subject},
            )
        except Exception:  # noqa: BLE001 - provider exceptions are intentionally redacted
            return PushSendResult(status_code=503)
        retry_after = None
        with suppress(AttributeError, TypeError, ValueError):
            retry_after = int(response.headers.get("retry-after", ""))
        return PushSendResult(status_code=int(response.status_code), retry_after=retry_after)


class NotificationDispatcher:
    """Deliver one pending logical notice to all of its current subscriptions."""

    def __init__(
        self,
        session_factory: sessionmaker[DbSession],
        transport: PushTransport,
    ) -> None:
        self.session_factory = session_factory
        self.transport = transport

    def run_once(self) -> int:
        now = utc_now()
        with self.session_factory() as session:
            notice = session.scalar(
                select(NotificationOutbox)
                .where(
                    NotificationOutbox.status.in_(("pending", "dispatching")),
                    NotificationOutbox.available_at <= now,
                )
                .order_by(NotificationOutbox.id)
                .with_for_update(skip_locked=True)
            )
            if notice is None:
                return 0
            subscriptions = session.scalars(
                select(PushSubscription).where(PushSubscription.user_id == notice.user_id)
            ).all()
            for subscription in subscriptions:
                delivery = session.scalar(
                    select(NotificationDelivery).where(
                        NotificationDelivery.notification_id == notice.id,
                        NotificationDelivery.subscription_id == subscription.id,
                    )
                )
                if delivery is None:
                    session.add(
                        NotificationDelivery(
                            notification_id=notice.id,
                            subscription_id=subscription.id,
                            available_at=now,
                        )
                    )
            notice.status = "dispatching"
            session.commit()

        payload = _reauthentication_payload()
        attempted = 0
        with self.session_factory() as session:
            deliveries = session.scalars(
                select(NotificationDelivery)
                .where(
                    NotificationDelivery.notification_id == notice.id,
                    NotificationDelivery.status == "pending",
                    NotificationDelivery.available_at <= now,
                )
                .order_by(NotificationDelivery.id)
            ).all()
            for delivery in deliveries:
                current_subscription = session.get(PushSubscription, delivery.subscription_id)
                if current_subscription is None:
                    delivery.status = "failed"
                    continue
                attempted += 1
                session.expunge(delivery)
                session.expunge(current_subscription)
                result = self.transport.send(current_subscription, payload)
                self._record_result(delivery.id, result)
            session.commit()

        self._finish_notice(notice.id)
        return attempted

    def _record_result(self, delivery_id: int, result: PushSendResult) -> None:
        with self.session_factory() as session:
            delivery = session.get(NotificationDelivery, delivery_id)
            if delivery is None:
                return
            delivery.attempts += 1
            if result.status_code in (404, 410):
                subscription = session.get(PushSubscription, delivery.subscription_id)
                if subscription is not None:
                    session.delete(subscription)
                session.commit()
                return
            if 200 <= result.status_code < 300:
                delivery.status = "delivered"
                delivery.delivered_at = utc_now()
                delivery.last_error = None
            elif result.status_code == 429 or result.status_code >= 500:
                delivery.status = "pending"
                delivery.available_at = utc_now() + timedelta(
                    seconds=max(30, result.retry_after or 300)
                )
                delivery.last_error = "temporary push delivery failure"
            else:
                delivery.status = "failed"
                delivery.last_error = "permanent push delivery failure"
            session.commit()

    def _finish_notice(self, notice_id: int) -> None:
        with self.session_factory() as session:
            notice = session.get(NotificationOutbox, notice_id)
            if notice is None:
                return
            pending = session.scalar(
                select(NotificationDelivery.id).where(
                    NotificationDelivery.notification_id == notice_id,
                    NotificationDelivery.status == "pending",
                )
            )
            if pending is None:
                notice.status = "delivered"
                notice.delivered_at = utc_now()
            else:
                next_available = session.scalar(
                    select(NotificationDelivery.available_at)
                    .where(
                        NotificationDelivery.notification_id == notice_id,
                        NotificationDelivery.status == "pending",
                    )
                    .order_by(NotificationDelivery.available_at)
                )
                notice.status = "pending"
                notice.available_at = next_available or utc_now()
            session.commit()


def _reauthentication_payload() -> str:
    return json.dumps(
        {
            "title": "Reconnect required",
            "body": "Reconnect CampusWeb to resume attendance refresh.",
            "tag": "srm-reauthentication",
            "url": "/?reconnect=1",
        },
        separators=(",", ":"),
    )
