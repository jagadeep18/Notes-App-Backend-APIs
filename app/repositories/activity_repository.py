"""app/repositories/activity_repository.py"""
from __future__ import annotations

from uuid import UUID

from sqlalchemy import and_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.activity import ActionType, ActivityLog
from app.repositories.base_repository import BaseRepository
from app.schemas.common import PaginationParams


class ActivityRepository(BaseRepository[ActivityLog]):
    model = ActivityLog

    async def log(
        self,
        user_id: UUID | None,
        action_type: ActionType,
        note_id: UUID | None = None,
        metadata: dict | None = None,
    ) -> ActivityLog:
        return await self.create(
            user_id=user_id,
            action_type=action_type,
            note_id=note_id,
            extra_data=metadata,  # column is extra_data, param stays as metadata for callers
        )

    async def get_user_activity(
        self,
        user_id: UUID,
        pagination: PaginationParams,
        action_type: ActionType | None = None,
        note_id: UUID | None = None,
    ) -> tuple[list[ActivityLog], int]:
        from sqlalchemy import func

        filters = [ActivityLog.user_id == user_id]
        if action_type:
            filters.append(ActivityLog.action_type == action_type)
        if note_id:
            filters.append(ActivityLog.note_id == note_id)

        base_q = select(ActivityLog).where(and_(*filters))

        count_q = select(func.count()).select_from(base_q.subquery())
        total = (await self._session.execute(count_q)).scalar_one()

        logs = (
            await self._session.execute(
                base_q.order_by(ActivityLog.created_at.desc())
                .offset(pagination.offset)
                .limit(pagination.limit)
            )
        ).scalars().all()

        return list(logs), total
