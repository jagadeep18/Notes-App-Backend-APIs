"""app/services/activity_service.py"""
from __future__ import annotations

from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession

from app.models.activity import ActionType
from app.repositories.activity_repository import ActivityRepository
from app.schemas.common import PaginationParams


class ActivityService:
    def __init__(self, session: AsyncSession) -> None:
        self._repo = ActivityRepository(session)

    async def get_user_timeline(
        self,
        user_id: UUID,
        pagination: PaginationParams,
        action_type: ActionType | None = None,
        note_id: UUID | None = None,
    ) -> tuple[list, int]:
        return await self._repo.get_user_activity(
            user_id=user_id,
            pagination=pagination,
            action_type=action_type,
            note_id=note_id,
        )
