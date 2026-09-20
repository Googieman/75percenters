"""Authenticated encryption for server-side SRM session material."""

import base64
import binascii
import json
import secrets
from collections.abc import Mapping

from cryptography.exceptions import InvalidTag
from cryptography.hazmat.primitives.ciphers.aead import AESGCM


class SessionCipherError(ValueError):
    """Raised when encrypted session material cannot be safely used."""


class SessionCipher:
    """Encrypt opaque provider state with owner-bound authenticated context."""

    NONCE_SIZE = 12
    KEY_SIZE = 32

    def __init__(self, key: bytes, key_version: int = 1) -> None:
        if len(key) != self.KEY_SIZE:
            raise SessionCipherError("session encryption key must contain 32 bytes")
        if key_version <= 0:
            raise SessionCipherError("session encryption key version must be positive")
        self._aes = AESGCM(key)
        self.key_version = key_version

    @classmethod
    def from_base64(cls, encoded_key: str, key_version: int = 1) -> "SessionCipher":
        try:
            key = base64.urlsafe_b64decode(encoded_key.encode("ascii"))
        except (UnicodeEncodeError, binascii.Error) as error:
            raise SessionCipherError("session encryption key is not valid base64") from error
        return cls(key, key_version)

    def encrypt(
        self,
        plaintext: bytes,
        *,
        owner_id: int,
        provider: str,
        generation: int,
        binding_id: int | None = None,
    ) -> bytes:
        nonce = secrets.token_bytes(self.NONCE_SIZE)
        return nonce + self._aes.encrypt(
            nonce,
            plaintext,
            self._associated_data(owner_id, provider, generation, binding_id),
        )

    def decrypt(
        self,
        encrypted: bytes,
        *,
        owner_id: int,
        provider: str,
        generation: int,
        binding_id: int | None = None,
    ) -> bytes:
        if len(encrypted) <= self.NONCE_SIZE:
            raise SessionCipherError("encrypted session state is truncated")
        nonce = encrypted[: self.NONCE_SIZE]
        ciphertext = encrypted[self.NONCE_SIZE :]
        try:
            return self._aes.decrypt(
                nonce,
                ciphertext,
                self._associated_data(owner_id, provider, generation, binding_id),
            )
        except InvalidTag as error:
            raise SessionCipherError("encrypted session state failed authentication") from error

    @staticmethod
    def _associated_data(
        owner_id: int, provider: str, generation: int, binding_id: int | None
    ) -> bytes:
        if (
            owner_id <= 0
            or generation <= 0
            or not provider
            or binding_id is not None
            and binding_id <= 0
        ):
            raise SessionCipherError("invalid session binding")
        suffix = f"/{binding_id}" if binding_id is not None else ""
        return f"srm-tracker/session/{owner_id}/{provider}/{generation}{suffix}".encode()


class SessionKeyring:
    """Hold the active write key and still-readable session key versions."""

    def __init__(self, ciphers: Mapping[int, SessionCipher], active_version: int) -> None:
        if not ciphers:
            raise SessionCipherError("session keyring cannot be empty")
        if active_version not in ciphers:
            raise SessionCipherError("active session key version is unavailable")
        self._ciphers = dict(ciphers)
        self.active_version = active_version

    @classmethod
    def from_base64(cls, keys: Mapping[int, str], *, active_version: int) -> "SessionKeyring":
        return cls(
            {
                version: SessionCipher.from_base64(encoded, key_version=version)
                for version, encoded in keys.items()
            },
            active_version,
        )

    @property
    def readable_versions(self) -> tuple[int, ...]:
        return tuple(sorted(self._ciphers))

    @property
    def key_version(self) -> int:
        return self.active_version

    def cipher(self, version: int) -> SessionCipher:
        try:
            return self._ciphers[version]
        except KeyError as error:
            raise SessionCipherError("session encryption key version is unavailable") from error

    def encrypt(
        self,
        plaintext: bytes,
        *,
        owner_id: int,
        provider: str,
        generation: int,
        binding_id: int | None = None,
    ) -> bytes:
        return self.cipher(self.active_version).encrypt(
            plaintext,
            owner_id=owner_id,
            provider=provider,
            generation=generation,
            binding_id=binding_id,
        )

    def decrypt(
        self,
        encrypted: bytes,
        *,
        version: int,
        owner_id: int,
        provider: str,
        generation: int,
        binding_id: int | None = None,
    ) -> bytes:
        return self.cipher(version).decrypt(
            encrypted,
            owner_id=owner_id,
            provider=provider,
            generation=generation,
            binding_id=binding_id,
        )

    def rotate(
        self,
        encrypted: bytes,
        *,
        old_version: int,
        owner_id: int,
        provider: str,
        generation: int,
        binding_id: int | None = None,
    ) -> bytes:
        plaintext = self.decrypt(
            encrypted,
            version=old_version,
            owner_id=owner_id,
            provider=provider,
            generation=generation,
            binding_id=binding_id,
        )
        return self.encrypt(
            plaintext,
            owner_id=owner_id,
            provider=provider,
            generation=generation,
            binding_id=binding_id,
        )


def keyring_from_settings(
    active_key: str,
    *,
    active_version: int,
    read_keys_json: str | None = None,
) -> SessionKeyring:
    """Build a keyring from one active key and optional JSON read-key map."""
    keys: dict[int, str] = {active_version: active_key}
    if read_keys_json:
        try:
            configured = json.loads(read_keys_json)
        except json.JSONDecodeError as error:
            raise SessionCipherError("session read keys are not valid JSON") from error
        if not isinstance(configured, dict):
            raise SessionCipherError("session read keys must be a JSON object")
        for version, encoded in configured.items():
            if (
                not isinstance(version, str)
                or not version.isdigit()
                or not isinstance(encoded, str)
            ):
                raise SessionCipherError("session read keys have an invalid entry")
            parsed_version = int(version)
            if parsed_version == active_version:
                raise SessionCipherError("active session key must not be repeated as a read key")
            keys[parsed_version] = encoded
    return SessionKeyring.from_base64(keys, active_version=active_version)
