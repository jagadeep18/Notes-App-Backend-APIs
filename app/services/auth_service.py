"""
app/services/auth_service.py
─────────────────────────────
Authentication business logic.

Design: Service layer is framework-agnostic. No FastAPI imports here.
Services only depend on repositories and core utilities.
This makes them independently unit-testable with async test frameworks.
"""
from __future__ import annotations

from datetime import UTC, datetime
from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.exceptions import (
    ConflictError,
    InvalidCredentialsError,
    InvalidTokenError,
)
from app.core.security import (
    TokenType,
    create_access_token,
    create_refresh_token,
    decode_token,
    hash_password,
    verify_password,
    _hash_token,
)
from app.core.config import get_settings
from app.models.activity import ActionType
from app.models.user import User
from app.repositories.activity_repository import ActivityRepository
from app.repositories.user_repository import UserRepository
from app.schemas.user import LoginRequest, UserRegisterRequest

settings = get_settings()


class AuthService:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session
        self._user_repo = UserRepository(session)
        self._activity_repo = ActivityRepository(session)

    async def register(self, data: UserRegisterRequest) -> User:
        # Check uniqueness — do both checks before hashing password (avoid wasted bcrypt work)
        if await self._user_repo.email_exists(data.email):
            raise ConflictError("Email already registered")
        
        username = data.username
        if not username:
            # Generate username from email prefix
            base_username = data.email.split("@")[0]
            # Ensure it matches the pattern and is unique
            username = base_username[:50] # Limit to 50 chars
            # Simple collision avoidance
            if await self._user_repo.username_exists(username):
                import secrets
                username = f"{username[:45]}_{secrets.token_hex(2)}"

        if await self._user_repo.username_exists(username):
            raise ConflictError("Username already taken")

        user = await self._user_repo.create(
            username=username,
            email=data.email,
            hashed_password=hash_password(data.password),
            full_name=data.full_name,
            is_active=True,
            is_verified=False,
        )

        await self._activity_repo.log(
            user_id=user.id,
            action_type=ActionType.USER_REGISTERED,
            metadata={"email": user.email},
        )

        return user

    async def login(self, data: LoginRequest, ip_address: str | None = None) -> dict:
        user = await self._user_repo.get_by_email(data.email)

        # Timing-safe: always run verify even if user doesn't exist (prevents timing oracle)
        # This is a real bcrypt hash of a random string, never matching any real password
        dummy_hash = "$2b$04$xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx"
        try:
            password_ok = verify_password(data.password, user.hashed_password if user else dummy_hash)
        except Exception:
            password_ok = False

        if not user or not password_ok:
            raise InvalidCredentialsError("Invalid email or password")

        if not user.is_active:
            raise InvalidCredentialsError("Account has been deactivated")

        # Create tokens
        access_token = create_access_token(str(user.id))
        refresh_token = create_refresh_token(str(user.id))

        # Store refresh token hash for server-side revocation
        user.refresh_token_hash = _hash_token(refresh_token)
        user.last_login_at = datetime.now(UTC)
        await self._user_repo.save(user)

        await self._activity_repo.log(
            user_id=user.id,
            action_type=ActionType.USER_LOGIN,
            metadata={"ip_address": ip_address},
        )

        return {
            "access_token": access_token,
            "refresh_token": refresh_token,
            "token_type": "bearer",
            "expires_in": settings.access_token_expire_minutes * 60,
        }

    async def refresh(self, refresh_token: str) -> dict:
        try:
            payload = decode_token(refresh_token, expected_type=TokenType.REFRESH)
        except Exception as exc:
            raise InvalidTokenError("Invalid refresh token") from exc

        user = await self._user_repo.get_by_id(UUID(payload["sub"]))
        if not user or not user.is_active:
            raise InvalidTokenError("User not found or deactivated")

        # Validate against stored hash — prevents refresh token reuse after logout
        stored_hash = user.refresh_token_hash
        if not stored_hash or stored_hash != _hash_token(refresh_token):
            raise InvalidTokenError("Refresh token has been revoked")

        new_access = create_access_token(str(user.id))
        new_refresh = create_refresh_token(str(user.id))

        user.refresh_token_hash = _hash_token(new_refresh)
        await self._user_repo.save(user)

        return {
            "access_token": new_access,
            "refresh_token": new_refresh,
            "token_type": "bearer",
            "expires_in": settings.access_token_expire_minutes * 60,
        }

    async def logout(self, user: User) -> None:
        user.refresh_token_hash = None  # Invalidate all refresh tokens
        await self._user_repo.save(user)
        await self._activity_repo.log(
            user_id=user.id,
            action_type=ActionType.USER_LOGOUT,
        )
