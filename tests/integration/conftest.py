"""
tests/integration/conftest.py
──────────────────────────────
Integration test fixtures: DB setup, HTTP client, user helpers.
"""
from __future__ import annotations

from collections.abc import AsyncGenerator

import pytest
import pytest_asyncio
from httpx import ASGITransport, AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from app.db.base import Base
from app.db.session import get_db_session
from app.main import create_app

TEST_DB_URL = "sqlite+aiosqlite:///./test.db"

test_engine = create_async_engine(TEST_DB_URL, echo=False)
TestSessionLocal = async_sessionmaker(test_engine, expire_on_commit=False, autoflush=False)


@pytest_asyncio.fixture(scope="session", autouse=True)
async def create_test_tables() -> AsyncGenerator[None, None]:
    """Create all tables once for the whole integration test session."""
    async with test_engine.begin() as conn:
        await conn.run_sync(lambda c: Base.metadata.create_all(c, checkfirst=True))
    yield
    async with test_engine.begin() as conn:
        await conn.run_sync(Base.metadata.drop_all)


@pytest_asyncio.fixture
async def db_session() -> AsyncGenerator[AsyncSession, None]:
    """Provide a request-scoped session that rolls back after each test."""
    async with TestSessionLocal() as session:
        try:
            yield session
        finally:
            await session.rollback()


@pytest_asyncio.fixture
async def client(db_session: AsyncSession) -> AsyncGenerator[AsyncClient, None]:
    """HTTP test client with DB session dependency override."""
    app = create_app()

    async def override_get_db() -> AsyncGenerator[AsyncSession, None]:
        yield db_session

    app.dependency_overrides[get_db_session] = override_get_db

    async with AsyncClient(
        transport=ASGITransport(app=app), base_url="http://test"
    ) as c:
        yield c


@pytest_asyncio.fixture
async def registered_user(client: AsyncClient) -> dict:
    """Register a test user and return user info + auth tokens."""
    import time
    suffix = str(int(time.time() * 1000))[-6:]
    payload = {
        "username": f"testuser{suffix}",
        "email": f"test{suffix}@example.com",
        "password": "Test@1234",
        "full_name": "Test User",
    }
    resp = await client.post("/api/v1/auth/register", json=payload)
    assert resp.status_code == 201, resp.text

    login_resp = await client.post(
        "/api/v1/auth/login",
        json={"email": payload["email"], "password": "Test@1234"},
    )
    tokens = login_resp.json()
    return {
        "user": resp.json(),
        "tokens": tokens,
        "email": payload["email"],
        "headers": {"Authorization": f"Bearer {tokens['access_token']}"},
    }


@pytest_asyncio.fixture
async def second_user(client: AsyncClient) -> dict:
    import time
    suffix = str(int(time.time() * 1000))[-6:]
    payload = {
        "username": f"other{suffix}",
        "email": f"other{suffix}@example.com",
        "password": "Other@5678",
    }
    resp = await client.post("/api/v1/auth/register", json=payload)
    assert resp.status_code == 201, resp.text
    login_resp = await client.post(
        "/api/v1/auth/login",
        json={"email": payload["email"], "password": "Other@5678"},
    )
    tokens = login_resp.json()
    return {
        "user": resp.json(),
        "tokens": tokens,
        "email": payload["email"],
        "headers": {"Authorization": f"Bearer {tokens['access_token']}"},
    }
