"""Authenticated encryption for server-side SRM session material."""

import base64
import binascii
import secrets

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

    def encrypt(self, plaintext: bytes, *, owner_id: int, provider: str, generation: int) -> bytes:
        nonce = secrets.token_bytes(self.NONCE_SIZE)
        return nonce + self._aes.encrypt(
            nonce, plaintext, self._associated_data(owner_id, provider, generation)
        )

    def decrypt(self, encrypted: bytes, *, owner_id: int, provider: str, generation: int) -> bytes:
        if len(encrypted) <= self.NONCE_SIZE:
            raise SessionCipherError("encrypted session state is truncated")
        nonce = encrypted[: self.NONCE_SIZE]
        ciphertext = encrypted[self.NONCE_SIZE :]
        try:
            return self._aes.decrypt(
                nonce,
                ciphertext,
                self._associated_data(owner_id, provider, generation),
            )
        except InvalidTag as error:
            raise SessionCipherError("encrypted session state failed authentication") from error

    @staticmethod
    def _associated_data(owner_id: int, provider: str, generation: int) -> bytes:
        if owner_id <= 0 or generation <= 0 or not provider:
            raise SessionCipherError("invalid session binding")
        return f"srm-tracker/session/{owner_id}/{provider}/{generation}".encode()
