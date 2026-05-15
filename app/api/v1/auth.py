"""
app/api/v1/auth.py
──────────────────
Auth endpoints: register, login, refresh, logout, me.
Spec-compliant paths and response formats.
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
    "/register",
    status_code=status.HTTP_201_CREATED,
    summary="Register a new user",
)
async def register(
    payload: UserRegisterRequest,
    db: DbSession,
) -> dict:
    """
    Create a new account.
    Spec: POST /register with {email, password} → 201 with success message.
    """
    service = AuthService(db)
    user = await service.register(payload)
    return {"message": "User registered successfully", "id": str(user.id), "email": user.email}


@router.post(
    "/login",
    response_model=TokenResponse,
    summary="Login and receive JWT token",
)
async def login(
    payload: LoginRequest,
    request: Request,
    db: DbSession,
) -> TokenResponse:
    """
    Authenticate and receive access token.
    Spec: POST /login → 200 {access_token} or 401 {message}.
    """
    ip_address = request.client.host if request.client else None
    service = AuthService(db)
    tokens = await service.login(payload, ip_address=ip_address)
    return TokenResponse(access_token=tokens["access_token"])


@router.post(
    "/refresh",
    response_model=TokenResponse,
    summary="Rotate tokens using refresh token",
)
async def refresh_token(
    payload: RefreshTokenRequest,
    db: DbSession,
) -> TokenResponse:
    service = AuthService(db)
    tokens = await service.refresh(payload.refresh_token)
    return TokenResponse(access_token=tokens["access_token"])


@router.post(
    "/logout",
    response_model=MessageResponse,
    summary="Logout",
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
