"""
app/models/note.py
──────────────────
Note, NoteShare, NoteVersion, ShareLink models.

Design decisions:
- Soft delete (deleted_at timestamp) preserves audit trail and enables
  version restore even after deletion — hard delete would lose history.
- Full-text search via PostgreSQL tsvector + GIN index — no Elasticsearch
  needed for this scale. The tsvector is maintained by a DB trigger.
- is_private + content encrypted at rest; encryption_key_version tracks
  which Fernet key was used for future key rotation.
- NoteShare uses a composite unique constraint on (note_id, shared_with_id)
  so duplicate shares are prevented at DB level, not just application level.
"""
from __future__ import annotations

import uuid
from datetime import datetime
from enum import StrEnum

from sqlalchemy import (
    Boolean,
    DateTime,
    Enum,
    ForeignKey,
    Index,
    Integer,
    JSON,
    String,
    Text,
    UniqueConstraint,
    text,
)
from sqlalchemy.dialects.postgresql import UUID as PGUUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base


class NotePermission(StrEnum):
    READ = "read"
    WRITE = "write"


class ShareLinkExpiry(StrEnum):
    ONE_HOUR = "1h"
    ONE_DAY = "24h"
    SEVEN_DAYS = "7d"


class Note(Base):
    __tablename__ = "notes"

    owner_id: Mapped[uuid.UUID] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True
    )

    title: Mapped[str] = mapped_column(String(500), nullable=False)
    content: Mapped[str] = mapped_column(Text, nullable=False)

    # Encryption metadata
    is_private: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    encryption_key_version: Mapped[str | None] = mapped_column(String(10), nullable=True)

    # Pinning
    is_pinned: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False, index=True)
    pinned_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    # Soft delete
    deleted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    # Full-text search (populated by DB trigger on Postgres)
    # Using Text here for SQLite test compatibility; migration creates TSVECTOR + GIN on Postgres
    search_vector: Mapped[str | None] = mapped_column(Text, nullable=True, deferred=True)

    # ── Relationships ─────────────────────────────────────────────────────────
    owner: Mapped["User"] = relationship("User", back_populates="notes")  # type: ignore[name-defined]
    shares: Mapped[list["NoteShare"]] = relationship(
        "NoteShare", back_populates="note", cascade="all, delete-orphan"
    )
    versions: Mapped[list["NoteVersion"]] = relationship(
        "NoteVersion", back_populates="note", cascade="all, delete-orphan", order_by="NoteVersion.version_number.desc()"
    )
    share_links: Mapped[list["ShareLink"]] = relationship(
        "ShareLink", back_populates="note", cascade="all, delete-orphan"
    )

    __table_args__ = (
        # GIN index for full-text search — O(1) vs O(n) sequential scan
        Index("ix_notes_search_vector", "search_vector", postgresql_using="gin"),
        # Filter out deleted notes efficiently
        Index("ix_notes_owner_active", "owner_id", postgresql_where=text("deleted_at IS NULL")),
        Index("ix_notes_pinned", "owner_id", "is_pinned", postgresql_where=text("deleted_at IS NULL AND is_pinned = TRUE")),
    )

    @property
    def is_deleted(self) -> bool:
        return self.deleted_at is not None

    def __repr__(self) -> str:
        short = repr(self.title[:30]) if self.title else "''"
        return f"<Note id={self.id} title={short}>"


class NoteShare(Base):
    __tablename__ = "note_shares"

    note_id: Mapped[uuid.UUID] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("notes.id", ondelete="CASCADE"), nullable=False
    )
    shared_with_id: Mapped[uuid.UUID] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), nullable=False
    )
    shared_by_id: Mapped[uuid.UUID] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), nullable=False
    )
    permission: Mapped[NotePermission] = mapped_column(
        Enum(NotePermission, name="note_permission_enum", create_type=False, values_callable=lambda obj: [e.value for e in obj]), default=NotePermission.READ, nullable=False
    )

    # Relationships
    note: Mapped["Note"] = relationship("Note", back_populates="shares")
    shared_with: Mapped["User"] = relationship("User", back_populates="shared_notes", foreign_keys=[shared_with_id])  # type: ignore[name-defined]
    shared_by: Mapped["User"] = relationship("User", foreign_keys=[shared_by_id])  # type: ignore[name-defined]

    __table_args__ = (
        UniqueConstraint("note_id", "shared_with_id", name="uq_note_share_per_user"),
        Index("ix_note_shares_shared_with", "shared_with_id"),
    )


class NoteVersion(Base):
    __tablename__ = "note_versions"

    note_id: Mapped[uuid.UUID] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("notes.id", ondelete="CASCADE"), nullable=False
    )
    version_number: Mapped[int] = mapped_column(Integer, nullable=False)
    title: Mapped[str] = mapped_column(String(500), nullable=False)
    content: Mapped[str] = mapped_column(Text, nullable=False)
    modified_by_id: Mapped[uuid.UUID] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL"), nullable=True
    )

    # Relationships
    note: Mapped["Note"] = relationship("Note", back_populates="versions")
    modified_by: Mapped["User"] = relationship("User", foreign_keys=[modified_by_id])  # type: ignore[name-defined]

    __table_args__ = (
        # Each (note_id, version_number) pair must be unique
        UniqueConstraint("note_id", "version_number", name="uq_note_version"),
        Index("ix_note_versions_note_id", "note_id", "version_number"),
    )

    def __repr__(self) -> str:
        return f"<NoteVersion note={self.note_id} v={self.version_number}>"


class ShareLink(Base):
    __tablename__ = "share_links"

    note_id: Mapped[uuid.UUID] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("notes.id", ondelete="CASCADE"), nullable=False, index=True
    )
    created_by_id: Mapped[uuid.UUID] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), nullable=False
    )

    # Store only the hash — raw token is delivered to the user, never persisted
    token_hash: Mapped[str] = mapped_column(String(64), unique=True, nullable=False, index=True)
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    access_count: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    max_accesses: Mapped[int | None] = mapped_column(Integer, nullable=True)  # None = unlimited
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)

    # Relationships
    note: Mapped["Note"] = relationship("Note", back_populates="share_links")
    created_by: Mapped["User"] = relationship("User", foreign_keys=[created_by_id])  # type: ignore[name-defined]

    @property
    def is_expired(self) -> bool:
        from datetime import UTC
        from datetime import datetime as dt
        return dt.now(UTC) > self.expires_at

    @property
    def is_one_time(self) -> bool:
        return self.max_accesses == 1
