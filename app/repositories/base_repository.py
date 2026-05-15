"""
app/repositories/base_repository.py
────────────────────────────────────
Generic async repository base.

Design: Repository pattern isolates data access from business logic.
Services don't know whether data comes from Postgres, Redis, or a test stub.
This makes unit testing trivial — swap the repo with an in-memory fake.
"""
from __future__ import annotations

from typing import Any, Generic, TypeVar
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.base import Base

ModelT = TypeVar("ModelT", bound=Base)


class BaseRepository(Generic[ModelT]):
    model: type[ModelT]

    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def get_by_id(self, id: UUID) -> ModelT | None:
        result = await self._session.execute(select(self.model).where(self.model.id == id))
        return result.scalar_one_or_none()

    async def create(self, **kwargs: Any) -> ModelT:
        instance = self.model(**kwargs)
        self._session.add(instance)
        await self._session.flush()  # flush to get DB-generated fields (id, created_at)
        await self._session.refresh(instance)
        return instance

    async def save(self, instance: ModelT) -> ModelT:
        self._session.add(instance)
        await self._session.flush()
        await self._session.refresh(instance)
        return instance

    async def delete(self, instance: ModelT) -> None:
        await self._session.delete(instance)
        await self._session.flush()
