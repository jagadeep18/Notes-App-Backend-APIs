"""
app/models/activity.py
──────────────────────
Activity/audit log model.

Design: Append-only table (no updates, no deletes via application layer).
This is the canonical audit trail. In production, this would live in
a separate schema or be streamed to a data warehouse for analytics.
"""
from __future__ import annotations

import uuid
from enum import StrEnum

from sqlalchemy import Enum, ForeignKey, Index, JSON, String
from sqlalchemy.dialects.postgresql import UUID as PGUUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base


class ActionType(StrEnum):
    # Auth
    USER_REGISTERED = "user_registered"
    USER_LOGIN = "user_login"
    USER_LOGOUT = "user_logout"

    # Notes CRUD
    NOTE_CREATED = "note_created"
    NOTE_UPDATED = "note_updated"
    NOTE_DELETED = "note_deleted"
    NOTE_RESTORED_FROM_TRASH = "note_restored_from_trash"

    # Sharing
    NOTE_SHARED = "note_shared"
    NOTE_UNSHARED = "note_unshared"
    NOTE_SHARE_LINK_CREATED = "note_share_link_created"
    NOTE_SHARE_LINK_ACCESSED = "note_share_link_accessed"

    # Version control
    NOTE_VERSION_RESTORED = "note_version_restored"

    # Pinning
    NOTE_PINNED = "note_pinned"
    NOTE_UNPINNED = "note_unpinned"

    # Private notes
    NOTE_ENCRYPTED = "note_encrypted"
    NOTE_DECRYPTED = "note_decrypted"


class ActivityLog(Base):
    __tablename__ = "activity_logs"

    user_id: Mapped[uuid.UUID | None] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey("users.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )
    action_type: Mapped[ActionType] = mapped_column(
        Enum(ActionType, name="action_type_enum", create_type=False), nullable=False
    )
    note_id: Mapped[uuid.UUID | None] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey("notes.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )
    # JSON: flexible metadata — use JSONB in production migration for indexability
    extra_data: Mapped[dict | None] = mapped_column(JSON, nullable=True)

    # Relationships
    user: Mapped["User"] = relationship("User", back_populates="activity_logs")  # type: ignore[name-defined]

    __table_args__ = (
        # Time-based queries (timeline view)
        Index("ix_activity_logs_user_created", "user_id", "created_at"),
        # Note-specific audit trail
        Index("ix_activity_logs_note", "note_id", "created_at"),
        # Action filtering
        Index("ix_activity_logs_action_type", "action_type"),
    )

    def __repr__(self) -> str:
        return f"<ActivityLog user={self.user_id} action={self.action_type}>"
