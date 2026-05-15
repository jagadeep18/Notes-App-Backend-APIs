"""
app/models/user.py
──────────────────
User model — the auth anchor for everything else.

Design decisions:
- email is the canonical identifier (unique, lowercase-normalized via DB check)
- is_active soft-disable without data loss
- refresh_token_hash for server-side refresh revocation (stateful refresh = security)
"""
from __future__ import annotations

import uuid
from datetime import datetime

from sqlalchemy import Boolean, DateTime, Index, String, text
from sqlalchemy.dialects.postgresql import UUID as PGUUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base


class User(Base):
    __tablename__ = "users"

    # Profile
    username: Mapped[str] = mapped_column(String(50), unique=True, nullable=False, index=True)
    email: Mapped[str] = mapped_column(String(255), unique=True, nullable=False, index=True)
    hashed_password: Mapped[str] = mapped_column(String(255), nullable=False)
    full_name: Mapped[str | None] = mapped_column(String(100), nullable=True)

    # State
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    is_verified: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    last_login_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    # Refresh token revocation (hash only — raw token never stored)
    refresh_token_hash: Mapped[str | None] = mapped_column(String(64), nullable=True)

    # ── Relationships ─────────────────────────────────────────────────────────
    notes: Mapped[list["Note"]] = relationship(  # type: ignore[name-defined]
        "Note", back_populates="owner", cascade="all, delete-orphan", passive_deletes=True
    )
    shared_notes: Mapped[list["NoteShare"]] = relationship(  # type: ignore[name-defined]
        "NoteShare", back_populates="shared_with", foreign_keys="NoteShare.shared_with_id"
    )
    activity_logs: Mapped[list["ActivityLog"]] = relationship(  # type: ignore[name-defined]
        "ActivityLog", back_populates="user", cascade="all, delete-orphan"
    )

    __table_args__ = (
        # Enforce lowercase email at DB level — app-level normalization isn't enough
        Index("ix_users_email_lower", text("lower(email)"), unique=True),
    )

    def __repr__(self) -> str:
        return f"<User id={self.id} username={self.username!r}>"
