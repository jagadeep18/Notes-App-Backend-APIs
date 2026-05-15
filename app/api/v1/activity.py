"""app/api/v1/activity.py — Activity timeline endpoint."""
from __future__ import annotations

from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, Query

from app.core.dependencies import CurrentUser, DbSession
from app.models.activity import ActionType
from app.schemas.activity import ActivityLogResponse
from app.schemas.common import PaginatedResponse, PaginationParams
from app.services.activity_service import ActivityService

router = APIRouter(prefix="/activity", tags=["Activity Timeline"])


def _get_pagination(
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=20, ge=1, le=100),
) -> PaginationParams:
    return PaginationParams(page=page, page_size=page_size)


@router.get(
    "",
    response_model=PaginatedResponse,
    summary="Get personal activity timeline",
)
async def get_activity(
    current_user: CurrentUser,
    db: DbSession,
    pagination: Annotated[PaginationParams, Depends(_get_pagination)],
    action_type: ActionType | None = Query(default=None, description="Filter by action type"),
    note_id: UUID | None = Query(default=None, description="Filter by note"),
) -> PaginatedResponse:
    """
    Returns a paginated, filterable audit trail of all user actions.
    Sorted by most recent first.
    """
    service = ActivityService(db)
    logs, total = await service.get_user_timeline(
        user_id=current_user.id,
        pagination=pagination,
        action_type=action_type,
        note_id=note_id,
    )
    items = [ActivityLogResponse.model_validate(log) for log in logs]
    return PaginatedResponse.create(items=items, total=total, pagination=pagination)
