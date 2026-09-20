"""Provider-neutral contracts for an evidence-approved SRM adapter."""

from dataclasses import dataclass
from typing import Protocol

from srm_tracker.schemas import AttendanceUpload


@dataclass(frozen=True, slots=True)
class ProviderChallenge:
    """Safe challenge metadata; state is opaque and stays server-side."""

    challenge_type: str | None
    message: str | None
    state: bytes | None


@dataclass(frozen=True, slots=True)
class ProviderSession:
    state: bytes
    verified_netid: str
    term_context: str


@dataclass(frozen=True, slots=True)
class HostedSyncResult:
    batch: AttendanceUpload
    term_context: str
    session_state: bytes | None = None


class AcquisitionProvider(Protocol):
    """The only boundary a concrete Student Portal/SCOPE adapter may implement."""

    name: str

    def start_authentication(self, netid: str) -> ProviderChallenge:
        """Begin authentication without receiving a password from storage or a queue."""

    def complete_authentication(
        self,
        challenge: ProviderChallenge,
        password: str,
        response: str | None,
    ) -> ProviderSession | ProviderChallenge:
        """Consume transient user input and return an opaque session or next challenge."""

    def fetch_attendance(self, session: ProviderSession) -> HostedSyncResult:
        """Fetch, verify, and normalize attendance without returning raw portal content."""

    def disconnect(self, session: ProviderSession) -> None:
        """Best-effort upstream logout when the provider supports it."""
