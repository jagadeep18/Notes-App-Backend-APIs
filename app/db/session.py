"""
app/db/session.py
─────────────────
Request-scoped database session dependency.

Design: Each HTTP request gets its own AsyncSession. The session is
committed on success and rolled back on any exception — ensuring
transactional integrity without boilerplate in every endpoint.
"""
from __future__ import annotations

from collections.abc import AsyncGenerator

from sqlalchemy.ext.asyncio import AsyncSession

from app.db.base import AsyncSessionLocal
from app.core.logging import get_logger

logger = get_logger(__name__)


async def get_db_session() -> AsyncGenerator[AsyncSession, None]:
    """FastAPI dependency that yields a request-scoped AsyncSession."""
    async with AsyncSessionLocal() as session:
        try:
            yield session
            await session.commit()
        except Exception:
            await session.rollback()
            raise
        finally:
            await session.close()
