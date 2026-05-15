"""app/schemas/activity.py — Activity log DTOs."""
from __future__ import annotations

from datetime import datetime
from uuid import UUID

from pydantic import BaseModel

from app.models.activity import ActionType


class ActivityLogResponse(BaseModel):
    id: UUID
    user_id: UUID | None
    action_type: ActionType
    note_id: UUID | None
    extra_data: dict | None
    created_at: datetime

    model_config = {"from_attributes": True}
