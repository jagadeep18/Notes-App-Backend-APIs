"""app/schemas/note.py — Note DTOs."""
from __future__ import annotations

from datetime import datetime
from enum import StrEnum
from uuid import UUID

from pydantic import BaseModel, Field, field_validator

from app.models.note import NotePermission, ShareLinkExpiry


class NoteCreateRequest(BaseModel):
    title: str = Field(min_length=1, max_length=500)
    content: str = Field(min_length=0, max_length=100_000)
    is_private: bool = False

    @field_validator("title")
    @classmethod
    def strip_title(cls, v: str) -> str:
        return v.strip()


class NoteUpdateRequest(BaseModel):
    title: str | None = Field(default=None, min_length=1, max_length=500)
    content: str | None = Field(default=None, max_length=100_000)
    is_private: bool | None = None


class NoteResponse(BaseModel):
    id: UUID
    owner_id: UUID
    title: str
    content: str  # decrypted on read
    is_private: bool
    is_pinned: bool
    pinned_at: datetime | None
    deleted_at: datetime | None
    created_at: datetime
    updated_at: datetime

    model_config = {"from_attributes": True}


class NoteShareRequest(BaseModel):
    user_id: UUID
    permission: NotePermission = NotePermission.READ


class NoteShareResponse(BaseModel):
    note_id: UUID
    shared_with_id: UUID
    permission: NotePermission
    created_at: datetime

    model_config = {"from_attributes": True}


class NoteVersionResponse(BaseModel):
    id: UUID
    note_id: UUID
    version_number: int
    title: str
    content: str
    modified_by_id: UUID | None
    created_at: datetime

    model_config = {"from_attributes": True}


class ShareLinkCreateRequest(BaseModel):
    expiry: ShareLinkExpiry = ShareLinkExpiry.ONE_DAY
    max_accesses: int | None = Field(default=None, ge=1, le=1000)

    class Config:
        use_enum_values = True


class ShareLinkResponse(BaseModel):
    token: str  # raw token — only returned on creation
    expires_at: datetime
    max_accesses: int | None
    access_count: int
    note_id: UUID


class SharedNoteResponse(BaseModel):
    """Public-facing note view via share link — no owner metadata exposed."""
    title: str
    content: str
    created_at: datetime
    updated_at: datetime
