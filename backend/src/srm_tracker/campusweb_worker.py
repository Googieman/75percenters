"""Worker-side CampusWeb session restoration and network execution."""

from sqlalchemy import select
from sqlalchemy.orm import Session as DbSession
from sqlalchemy.orm import sessionmaker

from srm_tracker.acquisition_crypto import SessionCipherError, SessionKeyring
from srm_tracker.acquisition_provider import (
    AcquisitionProvider,
    HostedSyncResult,
    ProviderSession,
)
from srm_tracker.campusweb_provider import (
    ProviderContractChanged as CampusContractChanged,
)
from srm_tracker.campusweb_provider import (
    ProviderReauthenticationRequired as CampusReauthenticationRequired,
)
from srm_tracker.campusweb_provider import (
    ProviderTransientFailure as CampusTransientFailure,
)
from srm_tracker.db_models import SrmConnection
from srm_tracker.session_store import decrypt_session_state
from srm_tracker.sync_jobs import JobClaim
from srm_tracker.worker import (
    ProviderContractChanged,
    ProviderReauthenticationRequired,
    ProviderTransientFailure,
)


class CampusWebSyncExecutor:
    """Restore encrypted state, then perform network work outside a DB transaction."""

    def __init__(
        self,
        session_factory: sessionmaker[DbSession],
        provider: AcquisitionProvider,
        keyring: SessionKeyring,
    ) -> None:
        self.session_factory = session_factory
        self.provider = provider
        self.keyring = keyring

    def fetch(self, claim: JobClaim) -> HostedSyncResult:
        with self.session_factory() as session:
            connection = session.scalar(
                select(SrmConnection).where(
                    SrmConnection.id == claim.connection_id,
                    SrmConnection.user_id == claim.user_id,
                    SrmConnection.generation == claim.connection_generation,
                    SrmConnection.status == "connected",
                )
            )
            if (
                connection is None
                or connection.verified_netid is None
                or connection.term_context is None
            ):
                raise ProviderReauthenticationRequired("connection is no longer active")
            try:
                encrypted = decrypt_session_state(connection, self.keyring)
            except SessionCipherError as error:
                raise ProviderReauthenticationRequired(
                    "CampusWeb session state is unavailable"
                ) from error
            provider_session = ProviderSession(
                state=encrypted,
                verified_netid=connection.verified_netid,
                term_context=connection.term_context,
            )
        try:
            return self.provider.fetch_attendance(provider_session)
        except CampusReauthenticationRequired as error:
            raise ProviderReauthenticationRequired("CampusWeb session expired") from error
        except CampusContractChanged as error:
            raise ProviderContractChanged("CampusWeb contract changed") from error
        except CampusTransientFailure as error:
            raise ProviderTransientFailure(
                "CampusWeb is temporarily unavailable", retry_after=error.retry_after
            ) from error
