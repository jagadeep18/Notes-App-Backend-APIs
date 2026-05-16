"""
app/api/v1/notes.py
────────────────────
Notes CRUD + sharing + pinning + version history + share links.
Every endpoint has:
  - Authorization check
  - Proper status codes
  - Consistent error propagation via exception handlers
"""
from __future__ import annotations

from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, Query, status
from fastapi.responses import Response

from app.core.dependencies import CurrentUser, DbSession
from app.models.note import NotePermission
from app.schemas.common import MessageResponse, PaginatedResponse, PaginationParams
from app.schemas.note import (
    NoteCreateRequest,
    NoteResponse,
    NoteShareRequest,
    NoteShareResponse,
    NoteUpdateRequest,
    NoteVersionResponse,
    ShareLinkCreateRequest,
    ShareLinkResponse,
    SharedNoteResponse,
)
from app.services.note_service import NoteService

router = APIRouter(prefix="/notes", tags=["Notes"])


def _get_pagination(
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=20, ge=1, le=100),
) -> PaginationParams:
    return PaginationParams(page=page, page_size=page_size)


PaginationDep = Annotated[PaginationParams, Depends(_get_pagination)]


# ── CRUD ─────────────────────────────────────────────────────────────────────


@router.post(
    "",
    response_model=NoteResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Create a note",
)
async def create_note(
    payload: NoteCreateRequest,
    current_user: CurrentUser,
    db: DbSession,
) -> NoteResponse:
    """
    Create a new note. Set `is_private=true` to encrypt content at rest.
    Private note content is decrypted transparently for authorized reads.
    """
    service = NoteService(db)
    note = await service.create_note(current_user, payload)
    return NoteResponse.model_validate(note)


@router.get(
    "",
    response_model=list[NoteResponse],
    summary="List all owned notes",
)
async def list_notes(
    current_user: CurrentUser,
    db: DbSession,
    pagination: PaginationDep,
    search: str | None = Query(default=None, description="Full-text search query"),
) -> list[NoteResponse]:
    """
    Returns owned notes. Pinned notes appear first.
    Supports full-text search across title and content.
    """
    service = NoteService(db)
    notes, total = await service.list_notes(current_user, pagination, search=search)
    return [NoteResponse.model_validate(n) for n in notes]


@router.get(
    "/shared",
    response_model=PaginatedResponse,
    summary="List notes shared with me",
)
async def list_shared_notes(
    current_user: CurrentUser,
    db: DbSession,
    pagination: PaginationDep,
) -> PaginatedResponse:
    service = NoteService(db)
    notes, total = await service.list_shared_notes(current_user, pagination)
    items = [NoteResponse.model_validate(n) for n in notes]
    return PaginatedResponse.create(items=items, total=total, pagination=pagination)


@router.get(
    "/{note_id}",
    response_model=NoteResponse,
    summary="Get a specific note",
)
async def get_note(
    note_id: UUID,
    current_user: CurrentUser,
    db: DbSession,
) -> NoteResponse:
    service = NoteService(db)
    note = await service.get_note(note_id, current_user)
    return NoteResponse.model_validate(note)


@router.put(
    "/{note_id}",
    response_model=NoteResponse,
    summary="Update a note",
)
async def update_note(
    note_id: UUID,
    payload: NoteUpdateRequest,
    current_user: CurrentUser,
    db: DbSession,
) -> NoteResponse:
    """
    Partial update — only provided fields are changed.
    Automatically saves previous state to version history.
    """
    service = NoteService(db)
    note = await service.update_note(note_id, current_user, payload)
    return NoteResponse.model_validate(note)


@router.delete(
    "/{note_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    response_model=None,
    summary="Soft-delete a note",
)
async def delete_note(
    note_id: UUID,
    current_user: CurrentUser,
    db: DbSession,
) -> None:
    """Soft-deletes a note. Data is retained for audit. Hard delete is not exposed."""
    service = NoteService(db)
    await service.delete_note(note_id, current_user)


# ── Sharing ───────────────────────────────────────────────────────────────────


@router.post(
    "/{note_id}/share",
    response_model=MessageResponse,
    status_code=status.HTTP_200_OK,
    summary="Share a note with a user",
)
async def share_note(
    note_id: UUID,
    payload: NoteShareRequest,
    current_user: CurrentUser,
    db: DbSession,
) -> MessageResponse:
    from app.repositories.user_repository import UserRepository
    from app.core.exceptions import NotFoundError
    
    user_repo = UserRepository(db)
    target_user = await user_repo.get_by_email(payload.share_with_email)
    if not target_user:
        raise NotFoundError("User with that email not found")
        
    service = NoteService(db)
    await service.share_note(note_id, current_user, target_user.id, payload.permission)
    return MessageResponse(message=f"Note shared successfully with {payload.share_with_email}")


@router.delete(
    "/{note_id}/share/{user_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    response_model=None,
    summary="Revoke note access from a user",
)
async def unshare_note(
    note_id: UUID,
    user_id: UUID,
    current_user: CurrentUser,
    db: DbSession,
) -> None:
    service = NoteService(db)
    await service.unshare_note(note_id, current_user, user_id)


@router.get(
    "/{note_id}/shares",
    response_model=list[NoteShareResponse],
    summary="Get users a note is shared with",
)
async def get_note_shares(
    note_id: UUID,
    current_user: CurrentUser,
    db: DbSession,
) -> list[NoteShareResponse]:
    service = NoteService(db)
    shares = await service.get_note_shares(note_id, current_user)
    return [NoteShareResponse.model_validate(s) for s in shares]


# ── Pinning ───────────────────────────────────────────────────────────────────


@router.post(
    "/{note_id}/pin",
    response_model=NoteResponse,
    summary="Pin a note (max 5)",
)
async def pin_note(
    note_id: UUID,
    current_user: CurrentUser,
    db: DbSession,
) -> NoteResponse:
    service = NoteService(db)
    note = await service.pin_note(note_id, current_user)
    return NoteResponse.model_validate(note)


@router.post(
    "/{note_id}/unpin",
    response_model=NoteResponse,
    summary="Unpin a note",
)
async def unpin_note(
    note_id: UUID,
    current_user: CurrentUser,
    db: DbSession,
) -> NoteResponse:
    service = NoteService(db)
    note = await service.unpin_note(note_id, current_user)
    return NoteResponse.model_validate(note)


# ── Version History ───────────────────────────────────────────────────────────


@router.get(
    "/{note_id}/versions",
    response_model=list[NoteVersionResponse],
    summary="Get version history of a note",
)
async def get_versions(
    note_id: UUID,
    current_user: CurrentUser,
    db: DbSession,
) -> list[NoteVersionResponse]:
    service = NoteService(db)
    versions = await service.get_versions(note_id, current_user)
    return [NoteVersionResponse.model_validate(v) for v in versions]


@router.get(
    "/{note_id}/versions/{version_number}",
    response_model=NoteVersionResponse,
    summary="Get a specific version of a note",
)
async def get_version(
    note_id: UUID,
    version_number: int,
    current_user: CurrentUser,
    db: DbSession,
) -> NoteVersionResponse:
    service = NoteService(db)
    version = await service.get_version(note_id, version_number, current_user)
    return NoteVersionResponse.model_validate(version)


@router.post(
    "/{note_id}/restore/{version_number}",
    response_model=NoteResponse,
    summary="Restore note to a previous version",
)
async def restore_version(
    note_id: UUID,
    version_number: int,
    current_user: CurrentUser,
    db: DbSession,
) -> NoteResponse:
    """
    Restores the note to a specific historical version.
    The current state is automatically snapshotted before restoring.
    """
    service = NoteService(db)
    note = await service.restore_version(note_id, version_number, current_user)
    return NoteResponse.model_validate(note)


# ── Share Links ───────────────────────────────────────────────────────────────


@router.post(
    "/{note_id}/share-link",
    response_model=ShareLinkResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Create a temporary share link",
)
async def create_share_link(
    note_id: UUID,
    payload: ShareLinkCreateRequest,
    current_user: CurrentUser,
    db: DbSession,
) -> ShareLinkResponse:
    """
    Generate a secure, time-limited share link.
    The raw token is shown ONCE — it is never stored in the database.
    """
    service = NoteService(db)
    link, raw_token = await service.create_share_link(note_id, current_user, payload)
    return ShareLinkResponse(
        token=raw_token,
        expires_at=link.expires_at,
        max_accesses=link.max_accesses,
        access_count=link.access_count,
        note_id=link.note_id,
    )


# Public share link access (no auth required)
shared_router = APIRouter(prefix="/shared", tags=["Shared Links"])


@shared_router.get(
    "/{token}",
    response_model=SharedNoteResponse,
    summary="Access a note via share link (public)",
)
async def access_shared_note(
    token: str,
    db: DbSession,
) -> SharedNoteResponse:
    """
    Access a note using a share link. No authentication required.
    Returns limited note data (no owner metadata).
    """
    service = NoteService(db)
    note = await service.access_share_link(token)
    return SharedNoteResponse(
        title=note.title,
        content=note.content,
        created_at=note.created_at,
        updated_at=note.updated_at,
    )
