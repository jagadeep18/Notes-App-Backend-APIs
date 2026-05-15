"""
app/api/exception_handlers.py
──────────────────────────────
Centralized exception → HTTP response translation.

Design: Domain exceptions map to specific HTTP status codes here.
This keeps the translation logic in ONE place and out of services.
Any unhandled exception falls through to the 500 handler.
"""
from __future__ import annotations

import traceback

from fastapi import FastAPI, Request, status
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse

from app.core.exceptions import (
    AuthError,
    ConflictError,
    DecryptionError,
    InsufficientPermissionsError,
    InvalidCredentialsError,
    NoteDeletedError,
    NotFoundError,
    PinLimitExceededError,
    RateLimitError,
    ShareTokenExpiredError,
    ShareTokenInvalidError,
    ValidationError as DomainValidationError,
)
from app.core.logging import get_logger

logger = get_logger(__name__)


def _error_response(code: str, message: str, status_code: int, details: dict | None = None) -> JSONResponse:
    content = {"error": {"code": code, "message": message}}
    if details:
        content["error"]["details"] = details  # type: ignore[index]
    return JSONResponse(status_code=status_code, content=content)


def register_exception_handlers(app: FastAPI) -> None:
    @app.exception_handler(RequestValidationError)
    async def validation_error_handler(request: Request, exc: RequestValidationError) -> JSONResponse:
        # Flatten Pydantic validation errors into readable format
        errors = [
            {"field": ".".join(str(loc) for loc in e["loc"]), "message": e["msg"]}
            for e in exc.errors()
        ]
        return _error_response(
            code="VALIDATION_ERROR",
            message="Request validation failed",
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            details={"errors": errors},  # type: ignore[arg-type]
        )

    @app.exception_handler(InvalidCredentialsError)
    async def invalid_credentials_handler(request: Request, exc: InvalidCredentialsError) -> JSONResponse:
        return _error_response("INVALID_CREDENTIALS", exc.message, status.HTTP_401_UNAUTHORIZED)

    @app.exception_handler(AuthError)
    async def auth_error_handler(request: Request, exc: AuthError) -> JSONResponse:
        return _error_response("AUTH_ERROR", exc.message, status.HTTP_401_UNAUTHORIZED)

    @app.exception_handler(InsufficientPermissionsError)
    async def permission_error_handler(request: Request, exc: InsufficientPermissionsError) -> JSONResponse:
        return _error_response("FORBIDDEN", exc.message, status.HTTP_403_FORBIDDEN)

    @app.exception_handler(NotFoundError)
    async def not_found_handler(request: Request, exc: NotFoundError) -> JSONResponse:
        return _error_response("NOT_FOUND", exc.message, status.HTTP_404_NOT_FOUND)

    @app.exception_handler(NoteDeletedError)
    async def deleted_note_handler(request: Request, exc: NoteDeletedError) -> JSONResponse:
        return _error_response("NOTE_DELETED", exc.message, status.HTTP_410_GONE)

    @app.exception_handler(ConflictError)
    async def conflict_handler(request: Request, exc: ConflictError) -> JSONResponse:
        return _error_response("CONFLICT", exc.message, status.HTTP_409_CONFLICT)

    @app.exception_handler(PinLimitExceededError)
    async def pin_limit_handler(request: Request, exc: PinLimitExceededError) -> JSONResponse:
        return _error_response("PIN_LIMIT_EXCEEDED", exc.message, status.HTTP_422_UNPROCESSABLE_ENTITY)

    @app.exception_handler(DomainValidationError)
    async def domain_validation_handler(request: Request, exc: DomainValidationError) -> JSONResponse:
        return _error_response("VALIDATION_ERROR", exc.message, status.HTTP_422_UNPROCESSABLE_ENTITY)

    @app.exception_handler(ShareTokenExpiredError)
    async def share_expired_handler(request: Request, exc: ShareTokenExpiredError) -> JSONResponse:
        return _error_response("SHARE_LINK_EXPIRED", exc.message, status.HTTP_410_GONE)

    @app.exception_handler(ShareTokenInvalidError)
    async def share_invalid_handler(request: Request, exc: ShareTokenInvalidError) -> JSONResponse:
        return _error_response("SHARE_LINK_INVALID", exc.message, status.HTTP_404_NOT_FOUND)

    @app.exception_handler(DecryptionError)
    async def decryption_error_handler(request: Request, exc: DecryptionError) -> JSONResponse:
        logger.error("decryption_failed", error=str(exc))
        return _error_response("DECRYPTION_ERROR", exc.message, status.HTTP_500_INTERNAL_SERVER_ERROR)

    @app.exception_handler(RateLimitError)
    async def rate_limit_handler(request: Request, exc: RateLimitError) -> JSONResponse:
        return _error_response("RATE_LIMIT_EXCEEDED", exc.message, status.HTTP_429_TOO_MANY_REQUESTS)

    @app.exception_handler(Exception)
    async def unhandled_exception_handler(request: Request, exc: Exception) -> JSONResponse:
        logger.error(
            "unhandled_exception",
            path=request.url.path,
            method=request.method,
            error=str(exc),
            traceback=traceback.format_exc(),
        )
        return _error_response(
            "INTERNAL_SERVER_ERROR",
            "An unexpected error occurred",
            status.HTTP_500_INTERNAL_SERVER_ERROR,
        )
