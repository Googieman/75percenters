import pytest
from pydantic import ValidationError

from srm_tracker.schemas import PushSubscriptionRequest


def _payload(endpoint: str) -> dict[str, object]:
    return {
        "endpoint": endpoint,
        "keys": {"p256dh": "public-key", "auth": "auth-secret"},
    }


def test_push_schema_accepts_supported_public_service() -> None:
    subscription = PushSubscriptionRequest.model_validate(
        _payload("https://fcm.googleapis.com/fcm/send/subscription-1")
    )

    assert str(subscription.endpoint).startswith("https://fcm.googleapis.com/")


@pytest.mark.parametrize(
    "endpoint",
    [
        "http://fcm.googleapis.com/fcm/send/1",
        "https://push.example/subscription/1",
        "https://127.0.0.1/push/1",
        "https://[::1]/push/1",
    ],
)
def test_push_schema_rejects_unsupported_or_private_destinations(endpoint: str) -> None:
    with pytest.raises(ValidationError):
        PushSubscriptionRequest.model_validate(_payload(endpoint))
