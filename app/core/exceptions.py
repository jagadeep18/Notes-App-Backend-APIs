"""
app/core/exceptions.py
──────────────────────
Centralized exception hierarchy.

Design decision: Domain-specific exceptions instead of raw HTTPException.
This decouples business logic from HTTP transport. Service layers raise
domain exceptions; the exception handlers translate them to HTTP responses.
This means services are independently testable without an HTTP context.
"""
from __future__ import annotations


class NotesBaseError(Exception):
    """Root exception for all application errors."""

    def __init__(self, message: str, details: dict | None = None) -> None:
        self.message = message
        self.details = details or {}
        super().__init__(message)


# ── Authentication & Authorization ────────────────────────────────────────────


class AuthError(NotesBaseError):
    """Base auth error."""


class InvalidCredentialsError(AuthError):
    """Wrong username/password."""


class InvalidTokenError(AuthError):
    """Malformed or invalid JWT."""


class TokenExpiredError(AuthError):
    """JWT has expired."""


class InsufficientPermissionsError(AuthError):
    """User lacks required permission."""


# ── Resource Errors ───────────────────────────────────────────────────────────


class NotFoundError(NotesBaseError):
    """Requested resource does not exist."""


class ConflictError(NotesBaseError):
    """Resource state conflict (duplicate, constraint violation)."""


class ValidationError(NotesBaseError):
    """Business-rule validation failed (distinct from Pydantic schema validation)."""


# ── Domain-specific ───────────────────────────────────────────────────────────


class PinLimitExceededError(ValidationError):
    """User has reached max pinned notes."""


class ShareTokenExpiredError(NotesBaseError):
    """Share link token is past its expiry."""


class ShareTokenInvalidError(NotesBaseError):
    """Share link token does not exist or was already consumed."""


class DecryptionError(NotesBaseError):
    """Cannot decrypt encrypted note — key mismatch or data corruption."""


class RateLimitError(NotesBaseError):
    """Too many requests."""


class NoteDeletedError(NotesBaseError):
    """Operation attempted on a soft-deleted note."""
