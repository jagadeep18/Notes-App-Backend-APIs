"""app/schemas/user.py — User DTOs (spec-compliant)."""
from __future__ import annotations

import re
from uuid import UUID
from datetime import datetime

from pydantic import BaseModel, EmailStr, Field, field_validator


USERNAME_RE = re.compile(r"^[a-zA-Z0-9_-]{3,50}$")


class UserRegisterRequest(BaseModel):
    """Spec: POST /register — only email and password required."""
    email: EmailStr
    password: str = Field(min_length=8, max_length=128)

    @field_validator("email")
    @classmethod
    def normalize_email(cls, v: str) -> str:
        return v.lower().strip()


class LoginRequest(BaseModel):
    email: EmailStr
    password: str

    @field_validator("email")
    @classmethod
    def normalize_email(cls, v: str) -> str:
        return v.lower().strip()


class TokenResponse(BaseModel):
    """Spec: login returns {"access_token": "string"}"""
    access_token: str


class RefreshTokenRequest(BaseModel):
    refresh_token: str


class UserResponse(BaseModel):
    id: UUID
    username: str
    email: str
    full_name: str | None
    is_active: bool
    is_verified: bool
    created_at: datetime
    last_login_at: datetime | None

    model_config = {"from_attributes": True}


class UserUpdateRequest(BaseModel):
    full_name: str | None = Field(default=None, max_length=100)

    model_config = {"from_attributes": True}
