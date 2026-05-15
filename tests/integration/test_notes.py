"""Integration tests for notes endpoints."""
from __future__ import annotations

import pytest
from httpx import AsyncClient


@pytest.mark.asyncio
class TestNotesCRUD:
    async def test_create_note(self, client: AsyncClient, registered_user: dict):
        resp = await client.post(
            "/api/v1/notes",
            json={"title": "My Note", "content": "Hello world"},
            headers=registered_user["headers"],
        )
        assert resp.status_code == 201
        data = resp.json()
        assert data["title"] == "My Note"
        assert data["content"] == "Hello world"
        assert data["is_pinned"] is False

    async def test_get_note(self, client: AsyncClient, registered_user: dict):
        cr = await client.post(
            "/api/v1/notes",
            json={"title": "Readable", "content": "Content here"},
            headers=registered_user["headers"],
        )
        note_id = cr.json()["id"]
        resp = await client.get(f"/api/v1/notes/{note_id}", headers=registered_user["headers"])
        assert resp.status_code == 200
        assert resp.json()["title"] == "Readable"

    async def test_update_note(self, client: AsyncClient, registered_user: dict):
        cr = await client.post(
            "/api/v1/notes",
            json={"title": "Old Title", "content": "Old"},
            headers=registered_user["headers"],
        )
        note_id = cr.json()["id"]
        resp = await client.put(
            f"/api/v1/notes/{note_id}",
            json={"title": "New Title"},
            headers=registered_user["headers"],
        )
        assert resp.status_code == 200
        assert resp.json()["title"] == "New Title"

    async def test_delete_note_returns_204(self, client: AsyncClient, registered_user: dict):
        cr = await client.post(
            "/api/v1/notes",
            json={"title": "To Delete", "content": "bye"},
            headers=registered_user["headers"],
        )
        note_id = cr.json()["id"]
        resp = await client.delete(f"/api/v1/notes/{note_id}", headers=registered_user["headers"])
        assert resp.status_code == 204

    async def test_unauthorized_access_rejected(self, client: AsyncClient, registered_user: dict, second_user: dict):
        cr = await client.post(
            "/api/v1/notes",
            json={"title": "Private", "content": "secret"},
            headers=registered_user["headers"],
        )
        note_id = cr.json()["id"]
        resp = await client.get(f"/api/v1/notes/{note_id}", headers=second_user["headers"])
        assert resp.status_code == 403


@pytest.mark.asyncio
class TestNotesPinning:
    async def test_pin_and_unpin_note(self, client: AsyncClient, registered_user: dict):
        cr = await client.post(
            "/api/v1/notes",
            json={"title": "Pin me", "content": "important"},
            headers=registered_user["headers"],
        )
        note_id = cr.json()["id"]

        pin_resp = await client.post(f"/api/v1/notes/{note_id}/pin", headers=registered_user["headers"])
        assert pin_resp.status_code == 200
        assert pin_resp.json()["is_pinned"] is True

        unpin_resp = await client.post(f"/api/v1/notes/{note_id}/unpin", headers=registered_user["headers"])
        assert unpin_resp.status_code == 200
        assert unpin_resp.json()["is_pinned"] is False

    async def test_duplicate_pin_rejected(self, client: AsyncClient, registered_user: dict):
        cr = await client.post(
            "/api/v1/notes",
            json={"title": "Double Pin", "content": "content"},
            headers=registered_user["headers"],
        )
        note_id = cr.json()["id"]
        await client.post(f"/api/v1/notes/{note_id}/pin", headers=registered_user["headers"])
        resp = await client.post(f"/api/v1/notes/{note_id}/pin", headers=registered_user["headers"])
        assert resp.status_code == 409
