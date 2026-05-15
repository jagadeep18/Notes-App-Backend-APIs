"""Integration tests for auth endpoints — root-level paths."""
from __future__ import annotations

import time

import pytest
from httpx import AsyncClient


def _unique_email(prefix: str = "user") -> str:
    return f"{prefix}{int(time.time()*1000)%1000000}@test.com"


@pytest.mark.asyncio
class TestAuthRegister:
    async def test_register_success(self, client: AsyncClient):
        email = _unique_email("reg")
        resp = await client.post("/signup", json={
            "username": f"reg{int(time.time()*1000)%1000000}",
            "email": email,
            "password": "NewUser@123",
        })
        assert resp.status_code == 201
        data = resp.json()
        assert data["email"] == email
        assert "hashed_password" not in data

    async def test_register_weak_password_rejected(self, client: AsyncClient):
        resp = await client.post("/signup", json={
            "username": "weakpw", "email": "weak@x.com", "password": "password"
        })
        assert resp.status_code == 422

    async def test_register_invalid_email(self, client: AsyncClient):
        resp = await client.post("/signup", json={
            "username": "badmail", "email": "not-an-email", "password": "Test@1234"
        })
        assert resp.status_code == 422


@pytest.mark.asyncio
class TestAuthLogin:
    async def test_login_success(self, client: AsyncClient, registered_user: dict):
        resp = await client.post("/login", json={
            "email": registered_user["email"], "password": "Test@1234"
        })
        assert resp.status_code == 200
        data = resp.json()
        assert "access_token" in data
        assert "refresh_token" in data
        assert data["token_type"] == "bearer"

    async def test_login_wrong_password(self, client: AsyncClient, registered_user: dict):
        resp = await client.post("/login", json={
            "email": registered_user["email"], "password": "WrongPass@1"
        })
        assert resp.status_code == 401

    async def test_login_nonexistent_email(self, client: AsyncClient):
        resp = await client.post("/login", json={
            "email": "ghost@example.com", "password": "Test@1234"
        })
        assert resp.status_code == 401

    async def test_get_me_with_valid_token(self, client: AsyncClient, registered_user: dict):
        resp = await client.get("/me", headers=registered_user["headers"])
        assert resp.status_code == 200
        assert resp.json()["email"] == registered_user["email"]

    async def test_get_me_without_token(self, client: AsyncClient):
        resp = await client.get("/me")
        assert resp.status_code == 401


@pytest.mark.asyncio
class TestAboutAndSearch:
    async def test_about_endpoint(self, client: AsyncClient):
        resp = await client.get("/about")
        assert resp.status_code == 200
        data = resp.json()
        assert "app" in data
        assert "features" in data
        assert len(data["features"]) > 0

    async def test_search_requires_auth(self, client: AsyncClient):
        resp = await client.get("/search?q=hello")
        assert resp.status_code == 401

    async def test_search_with_auth(self, client: AsyncClient, registered_user: dict):
        # Create a note first
        await client.post(
            "/notes", json={"title": "Searchable", "content": "unique_keyword_xyz"},
            headers=registered_user["headers"],
        )
        resp = await client.get("/search?q=unique_keyword", headers=registered_user["headers"])
        assert resp.status_code == 200
