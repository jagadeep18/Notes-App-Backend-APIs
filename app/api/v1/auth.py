"""
app/api/v1/auth.py
──────────────────
Auth endpoints: register, login, refresh, logout, me.
"""
from __future__ import annotations

from fastapi import APIRouter, Request, status

from app.core.dependencies import CurrentUser, DbSession
from app.schemas.user import (
    LoginRequest,
    RefreshTokenRequest,
    TokenResponse,
    UserRegisterRequest,
    UserResponse,
)
from app.schemas.common import MessageResponse
from app.services.auth_service import AuthService

router = APIRouter(tags=["Authentication"])


@router.post(
    "/signup",
    response_model=UserResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Register a new user",
)
async def register(
    payload: UserRegisterRequest,
    db: DbSession,
) -> UserResponse:
    """
    Create a new account.

    - **username**: 3–50 chars, alphanumeric + _-
    - **password**: min 8 chars, must include uppercase, digit, and special char
    - **email**: normalized to lowercase
    """
    service = AuthService(db)
    user = await service.register(payload)
    return UserResponse.model_validate(user)


@router.post(
    "/login",
    response_model=TokenResponse,
    summary="Login and receive JWT tokens",
)
async def login(
    payload: LoginRequest,
    request: Request,
    db: DbSession,
) -> TokenResponse:
    """
    Authenticate and receive access + refresh tokens.

    Access token expires in 30 minutes.
    Refresh token expires in 7 days.
    """
    ip_address = request.client.host if request.client else None
    service = AuthService(db)
    tokens = await service.login(payload, ip_address=ip_address)
    return TokenResponse(**tokens)


@router.post(
    "/refresh",
    response_model=TokenResponse,
    summary="Rotate tokens using refresh token",
)
async def refresh_token(
    payload: RefreshTokenRequest,
    db: DbSession,
) -> TokenResponse:
    """
    Exchange a valid refresh token for a new access + refresh token pair.
    The old refresh token is immediately invalidated (rotation strategy).
    """
    service = AuthService(db)
    tokens = await service.refresh(payload.refresh_token)
    return TokenResponse(**tokens)


@router.post(
    "/logout",
    response_model=MessageResponse,
    summary="Logout and invalidate refresh token",
)
async def logout(
    current_user: CurrentUser,
    db: DbSession,
) -> MessageResponse:
    service = AuthService(db)
    await service.logout(current_user)
    return MessageResponse(message="Logged out successfully")


@router.get(
    "/me",
    response_model=UserResponse,
    summary="Get current authenticated user",
)
async def get_me(current_user: CurrentUser) -> UserResponse:
    return UserResponse.model_validate(current_user)
