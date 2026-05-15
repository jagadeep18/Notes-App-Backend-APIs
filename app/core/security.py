"""
app/core/security.py
────────────────────
All cryptographic operations live here — one authoritative module.

Design decisions:
- bcrypt for passwords: adaptive cost factor protects against brute-force
  as hardware improves. Never MD5/SHA1/plain SHA256 for passwords.
- JWT with HS256 for simplicity; swap to RS256 for multi-service setups.
- Fernet (AES-128-CBC + HMAC-SHA256) for note encryption — symmetric,
  authenticated encryption. Key versioning supports zero-downtime rotation.
- Secure token generation uses secrets.token_urlsafe (CSPRNG).
"""
from __future__ import annotations

import hashlib
import secrets
from datetime import UTC, datetime, timedelta
from enum import StrEnum
from typing import Any

from cryptography.fernet import Fernet, InvalidToken
from jose import JWTError, jwt
from passlib.context import CryptContext

from app.core.config import get_settings
from app.core.exceptions import (
    DecryptionError,
    InvalidTokenError,
    TokenExpiredError,
)

settings = get_settings()

# 12 rounds in production (~250ms/hash — brute-force resistant)
# 4 rounds in dev/test (~1ms/hash — fast test feedback loop)
_bcrypt_rounds = 12 if settings.is_production else 4
_pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto", bcrypt__rounds=_bcrypt_rounds)

# Fernet cipher — initialized once, cached
_fernet = Fernet(settings.encryption_key.encode())


# ── Password ──────────────────────────────────────────────────────────────────


def hash_password(plain: str) -> str:
    return _pwd_context.hash(plain)


def verify_password(plain: str, hashed: str) -> bool:
    return _pwd_context.verify(plain, hashed)


# ── JWT ───────────────────────────────────────────────────────────────────────


class TokenType(StrEnum):
    ACCESS = "access"
    REFRESH = "refresh"


def create_access_token(subject: str, extra_claims: dict[str, Any] | None = None) -> str:
    """Create short-lived access token. subject = user UUID string."""
    return _create_token(
        subject=subject,
        token_type=TokenType.ACCESS,
        expires_delta=timedelta(minutes=settings.access_token_expire_minutes),
        extra_claims=extra_claims,
    )


def create_refresh_token(subject: str) -> str:
    """Create long-lived refresh token — stored reference in DB for revocation."""
    return _create_token(
        subject=subject,
        token_type=TokenType.REFRESH,
        expires_delta=timedelta(days=settings.refresh_token_expire_days),
    )


def _create_token(
    subject: str,
    token_type: TokenType,
    expires_delta: timedelta,
    extra_claims: dict[str, Any] | None = None,
) -> str:
    now = datetime.now(UTC)
    payload: dict[str, Any] = {
        "sub": subject,
        "type": token_type,
        "iat": now,
        "exp": now + expires_delta,
        "jti": secrets.token_hex(16),  # unique token ID for revocation
    }
    if extra_claims:
        payload.update(extra_claims)
    return jwt.encode(payload, settings.jwt_secret_key, algorithm=settings.jwt_algorithm)


def decode_token(token: str, expected_type: TokenType = TokenType.ACCESS) -> dict[str, Any]:
    """
    Decode and validate JWT. Raises typed exceptions for clean error handling.
    """
    try:
        payload = jwt.decode(
            token,
            settings.jwt_secret_key,
            algorithms=[settings.jwt_algorithm],
        )
    except JWTError as exc:
        # Check if it's specifically an expiry error for better UX
        if "expired" in str(exc).lower():
            raise TokenExpiredError("Access token has expired") from exc
        raise InvalidTokenError("Invalid token signature or structure") from exc

    if payload.get("type") != expected_type:
        raise InvalidTokenError(f"Expected {expected_type} token, got {payload.get('type')}")

    return payload


# ── Secure Share Tokens ───────────────────────────────────────────────────────


def generate_share_token() -> tuple[str, str]:
    """
    Returns (raw_token, hashed_token).
    Raw token is sent to the user; only the hash is stored in DB.
    This way, even a full DB compromise doesn't expose valid tokens.
    """
    raw = secrets.token_urlsafe(32)  # 256 bits of entropy
    hashed = _hash_token(raw)
    return raw, hashed


def hash_share_token(raw_token: str) -> str:
    return _hash_token(raw_token)


def _hash_token(token: str) -> str:
    """SHA-256 hash — sufficient for token storage (not passwords)."""
    return hashlib.sha256(token.encode()).hexdigest()


# ── Note Encryption ───────────────────────────────────────────────────────────


def encrypt_content(plaintext: str) -> tuple[str, str]:
    """
    Returns (ciphertext_b64, key_version).
    key_version allows decryption with old keys after rotation.
    """
    try:
        ciphertext = _fernet.encrypt(plaintext.encode()).decode()
        return ciphertext, settings.encryption_key_version
    except Exception as exc:
        raise DecryptionError("Failed to encrypt content") from exc


def decrypt_content(ciphertext: str) -> str:
    """Decrypt note content. Raises DecryptionError on invalid key/tampered data."""
    try:
        return _fernet.decrypt(ciphertext.encode()).decode()
    except InvalidToken as exc:
        raise DecryptionError(
            "Cannot decrypt note content — key mismatch or data corruption"
        ) from exc
