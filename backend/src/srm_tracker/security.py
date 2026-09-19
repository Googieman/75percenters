"""Password and opaque-token primitives."""

import hashlib
import secrets

from pwdlib import PasswordHash

PASSWORD_HASHER = PasswordHash.recommended()


def hash_password(password: str) -> str:
    """Hash a password with the maintained Argon2-backed pwdlib hasher."""
    return PASSWORD_HASHER.hash(password)


def verify_password(password: str, password_hash: str) -> bool:
    """Verify a password without exposing hash details to callers."""
    return PASSWORD_HASHER.verify(password, password_hash)


def new_opaque_token() -> str:
    """Generate a high-entropy value suitable for a session or device secret."""
    return secrets.token_urlsafe(32)


def hash_opaque_token(token: str) -> str:
    """Store only a deterministic SHA-256 digest of an opaque secret."""
    return hashlib.sha256(token.encode("utf-8")).hexdigest()
