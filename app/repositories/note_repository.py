"""app/repositories/note_repository.py"""
from __future__ import annotations

from uuid import UUID

from sqlalchemy import and_, func, or_, select, text
from sqlalchemy.orm import selectinload

from app.models.note import Note, NotePermission, NoteShare, NoteVersion, ShareLink
from app.repositories.base_repository import BaseRepository
from app.schemas.common import PaginationParams


class NoteRepository(BaseRepository[Note]):
    model = Note

    async def get_owned_notes(
        self,
        owner_id: UUID,
        pagination: PaginationParams,
        search: str | None = None,
        pinned_first: bool = True,
    ) -> tuple[list[Note], int]:
        """Return (notes, total_count) for list view with optional FTS."""
        base_q = (
            select(Note)
            .where(and_(Note.owner_id == owner_id, Note.deleted_at.is_(None)))
        )

        if search:
            # PostgreSQL: use tsvector FTS (fast, GIN-indexed)
            # SQLite fallback: ILIKE on title+content (for tests)
            db_url = str(self._session.bind.url) if self._session.bind else ""
            if "sqlite" in db_url:
                like_pattern = f"%{search}%"
                base_q = base_q.where(
                    or_(Note.title.ilike(like_pattern), Note.content.ilike(like_pattern))
                )
            else:
                base_q = base_q.where(
                    Note.search_vector.op("@@")(func.plainto_tsquery("english", search))
                )

        count_q = select(func.count()).select_from(base_q.subquery())
        total = (await self._session.execute(count_q)).scalar_one()

        if pinned_first:
            base_q = base_q.order_by(Note.is_pinned.desc(), Note.updated_at.desc())
        else:
            base_q = base_q.order_by(Note.updated_at.desc())

        base_q = base_q.offset(pagination.offset).limit(pagination.limit)
        notes = (await self._session.execute(base_q)).scalars().all()

        return list(notes), total

    async def get_shared_notes(
        self, user_id: UUID, pagination: PaginationParams
    ) -> tuple[list[Note], int]:
        """Notes shared with this user."""
        base_q = (
            select(Note)
            .join(NoteShare, NoteShare.note_id == Note.id)
            .where(
                and_(
                    NoteShare.shared_with_id == user_id,
                    Note.deleted_at.is_(None),
                )
            )
        )
        count_q = select(func.count()).select_from(base_q.subquery())
        total = (await self._session.execute(count_q)).scalar_one()

        notes = (
            await self._session.execute(
                base_q.order_by(Note.updated_at.desc())
                .offset(pagination.offset)
                .limit(pagination.limit)
            )
        ).scalars().all()

        return list(notes), total

    async def get_with_shares(self, note_id: UUID) -> Note | None:
        result = await self._session.execute(
            select(Note)
            .options(selectinload(Note.shares))
            .where(Note.id == note_id)
        )
        return result.scalar_one_or_none()

    async def count_pinned(self, owner_id: UUID) -> int:
        result = await self._session.execute(
            select(func.count()).where(
                and_(
                    Note.owner_id == owner_id,
                    Note.is_pinned.is_(True),
                    Note.deleted_at.is_(None),
                )
            )
        )
        return result.scalar_one()

    async def get_share(self, note_id: UUID, user_id: UUID) -> NoteShare | None:
        result = await self._session.execute(
            select(NoteShare).where(
                and_(
                    NoteShare.note_id == note_id,
                    NoteShare.shared_with_id == user_id,
                )
            )
        )
        return result.scalar_one_or_none()
        
    async def get_shares(self, note_id: UUID) -> list[NoteShare]:
        result = await self._session.execute(
            select(NoteShare)
            .options(selectinload(NoteShare.shared_with))
            .where(NoteShare.note_id == note_id)
        )
        return list(result.scalars().all())

    async def get_versions(self, note_id: UUID) -> list[NoteVersion]:
        result = await self._session.execute(
            select(NoteVersion)
            .where(NoteVersion.note_id == note_id)
            .order_by(NoteVersion.version_number.desc())
        )
        return list(result.scalars().all())

    async def get_version(self, note_id: UUID, version_number: int) -> NoteVersion | None:
        result = await self._session.execute(
            select(NoteVersion).where(
                and_(
                    NoteVersion.note_id == note_id,
                    NoteVersion.version_number == version_number,
                )
            )
        )
        return result.scalar_one_or_none()

    async def get_next_version_number(self, note_id: UUID) -> int:
        result = await self._session.execute(
            select(func.coalesce(func.max(NoteVersion.version_number), 0))
            .where(NoteVersion.note_id == note_id)
        )
        return result.scalar_one() + 1

    async def get_share_link_by_hash(self, token_hash: str) -> ShareLink | None:
        result = await self._session.execute(
            select(ShareLink)
            .options(selectinload(ShareLink.note))
            .where(ShareLink.token_hash == token_hash)
        )
        return result.scalar_one_or_none()
