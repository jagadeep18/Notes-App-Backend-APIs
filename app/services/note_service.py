"""
app/services/note_service.py
──────────────────────────────
Notes business logic: CRUD, sharing, pinning, versions, share links.
"""
from __future__ import annotations

from datetime import UTC, datetime, timedelta
from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import get_settings
from app.core.exceptions import (
    ConflictError,
    InsufficientPermissionsError,
    NoteDeletedError,
    NotFoundError,
    PinLimitExceededError,
    ShareTokenExpiredError,
    ShareTokenInvalidError,
)
from app.core.security import (
    decrypt_content,
    encrypt_content,
    generate_share_token,
    hash_share_token,
)
from app.models.activity import ActionType
from app.models.note import Note, NotePermission, NoteShare, NoteVersion, ShareLink, ShareLinkExpiry
from app.models.user import User
from app.repositories.activity_repository import ActivityRepository
from app.repositories.note_repository import NoteRepository
from app.schemas.common import PaginationParams
from app.schemas.note import (
    NoteCreateRequest,
    NoteUpdateRequest,
    ShareLinkCreateRequest,
)

settings = get_settings()

_EXPIRY_MAP: dict[ShareLinkExpiry, timedelta] = {
    ShareLinkExpiry.ONE_HOUR: timedelta(hours=1),
    ShareLinkExpiry.ONE_DAY: timedelta(hours=24),
    ShareLinkExpiry.SEVEN_DAYS: timedelta(days=7),
}


class NoteService:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session
        self._note_repo = NoteRepository(session)
        self._activity_repo = ActivityRepository(session)

    # ── CRUD ─────────────────────────────────────────────────────────────────

    async def create_note(self, owner: User, data: NoteCreateRequest) -> Note:
        title = data.title
        content = data.content
        encryption_key_version = None

        if data.is_private:
            content, encryption_key_version = encrypt_content(content)

        note = await self._note_repo.create(
            owner_id=owner.id,
            title=title,
            content=content,
            is_private=data.is_private,
            encryption_key_version=encryption_key_version,
        )

        await self._activity_repo.log(
            user_id=owner.id,
            action_type=ActionType.NOTE_CREATED,
            note_id=note.id,
            metadata={"title": title, "is_private": data.is_private},
        )

        return self._decrypt_note_for_response(note)

    async def get_note(self, note_id: UUID, user: User) -> Note:
        note = await self._note_repo.get_by_id(note_id)
        if not note:
            raise NotFoundError(f"Note {note_id} not found")
        if note.is_deleted:
            raise NoteDeletedError("Note has been deleted")

        await self._assert_can_read(note, user)
        return self._decrypt_note_for_response(note)

    async def list_notes(
        self,
        owner: User,
        pagination: PaginationParams,
        search: str | None = None,
    ) -> tuple[list[Note], int]:
        notes, total = await self._note_repo.get_owned_notes(owner.id, pagination, search)
        # Decrypt private notes for the owner
        decrypted = [self._decrypt_note_for_response(n) for n in notes]
        return decrypted, total

    async def list_shared_notes(
        self, user: User, pagination: PaginationParams
    ) -> tuple[list[Note], int]:
        notes, total = await self._note_repo.get_shared_notes(user.id, pagination)
        decrypted = [self._decrypt_note_for_response(n) for n in notes]
        return decrypted, total

    async def update_note(self, note_id: UUID, user: User, data: NoteUpdateRequest) -> Note:
        note = await self._note_repo.get_by_id(note_id)
        if not note:
            raise NotFoundError(f"Note {note_id} not found")
        if note.is_deleted:
            raise NoteDeletedError("Cannot update a deleted note")

        await self._assert_can_write(note, user)

        # Snapshot current state as a version BEFORE applying changes
        version_number = await self._note_repo.get_next_version_number(note_id)
        current_content = note.content
        if note.is_private:
            # Store plaintext in version history (it IS encrypted at rest via note content)
            current_content = decrypt_content(note.content)

        version = NoteVersion(
            note_id=note.id,
            version_number=version_number,
            title=note.title,
            content=current_content,
            modified_by_id=user.id,
        )
        self._session.add(version)

        # Apply updates
        if data.title is not None:
            note.title = data.title
        if data.content is not None:
            if note.is_private or data.is_private:
                note.content, note.encryption_key_version = encrypt_content(data.content)
            else:
                note.content = data.content
        if data.is_private is not None and data.is_private != note.is_private:
            if data.is_private:
                # If content was not updated in this request, we must encrypt the existing content
                if data.content is None:
                    note.content, note.encryption_key_version = encrypt_content(note.content)
            else:
                # Becoming public: decrypt current content
                if note.encryption_key_version:
                    note.content = decrypt_content(note.content)
                note.encryption_key_version = None
            note.is_private = data.is_private

        await self._note_repo.save(note)

        await self._activity_repo.log(
            user_id=user.id,
            action_type=ActionType.NOTE_UPDATED,
            note_id=note.id,
            metadata={"version_saved": version_number},
        )

        return self._decrypt_note_for_response(note)

    async def delete_note(self, note_id: UUID, user: User) -> None:
        note = await self._note_repo.get_by_id(note_id)
        if not note:
            raise NotFoundError(f"Note {note_id} not found")
        if note.is_deleted:
            raise NoteDeletedError("Note already deleted")
        if note.owner_id != user.id:
            raise InsufficientPermissionsError("Only the owner can delete a note")

        note.deleted_at = datetime.now(UTC)
        note.is_pinned = False
        note.pinned_at = None
        await self._note_repo.save(note)

        await self._activity_repo.log(
            user_id=user.id,
            action_type=ActionType.NOTE_DELETED,
            note_id=note.id,
        )

    # ── Sharing ──────────────────────────────────────────────────────────────

    async def share_note(
        self, note_id: UUID, owner: User, target_user_id: UUID, permission: NotePermission
    ) -> NoteShare:
        note = await self._note_repo.get_by_id(note_id)
        if not note:
            raise NotFoundError(f"Note {note_id} not found")
        if note.owner_id != owner.id:
            raise InsufficientPermissionsError("Only the owner can share a note")
        if target_user_id == owner.id:
            raise ConflictError("Cannot share a note with yourself")
        if note.is_deleted:
            raise NoteDeletedError("Cannot share a deleted note")

        existing = await self._note_repo.get_share(note_id, target_user_id)
        if existing:
            # Update permission if it changed (bonus feature)
            if existing.permission != permission:
                existing.permission = permission
                await self._session.flush()
                return existing
            raise ConflictError("Note already shared with this user")

        share = NoteShare(
            note_id=note.id,
            shared_with_id=target_user_id,
            shared_by_id=owner.id,
            permission=permission,
        )
        self._session.add(share)
        await self._session.flush()
        await self._session.refresh(share)

        # Simulate sending email notification
        from app.repositories.user_repository import UserRepository
        from app.services.email_service import EmailService
        user_repo = UserRepository(self._session)
        target_user = await user_repo.get_by_id(target_user_id)
        if target_user:
            await EmailService.send_share_notification(
                target_email=target_user.email,
                note_title=note.title,
                shared_by=owner.email
            )

        await self._activity_repo.log(
            user_id=owner.id,
            action_type=ActionType.NOTE_SHARED,
            note_id=note.id,
            metadata={"shared_with": str(target_user_id), "permission": permission},
        )

        return share

    async def unshare_note(self, note_id: UUID, owner: User, target_user_id: UUID) -> None:
        note = await self._note_repo.get_by_id(note_id)
        if not note or note.owner_id != owner.id:
            raise InsufficientPermissionsError("Not authorized")

        share = await self._note_repo.get_share(note_id, target_user_id)
        if not share:
            raise NotFoundError("Share not found")

        await self._note_repo.delete(share)

        await self._activity_repo.log(
            user_id=owner.id,
            action_type=ActionType.NOTE_UNSHARED,
            note_id=note.id,
            metadata={"removed_user": str(target_user_id)},
        )

    # ── Pinning ──────────────────────────────────────────────────────────────

    async def pin_note(self, note_id: UUID, user: User) -> Note:
        note = await self._note_repo.get_by_id(note_id)
        if not note:
            raise NotFoundError(f"Note {note_id} not found")
        if note.is_deleted:
            raise NoteDeletedError("Cannot pin a deleted note")
        if note.owner_id != user.id:
            raise InsufficientPermissionsError("Only the owner can pin a note")
        if note.is_pinned:
            raise ConflictError("Note is already pinned")

        pinned_count = await self._note_repo.count_pinned(user.id)
        if pinned_count >= settings.max_pinned_notes:
            raise PinLimitExceededError(
                f"Pin limit of {settings.max_pinned_notes} reached. Unpin another note first."
            )

        note.is_pinned = True
        note.pinned_at = datetime.now(UTC)
        await self._note_repo.save(note)

        await self._activity_repo.log(
            user_id=user.id, action_type=ActionType.NOTE_PINNED, note_id=note.id
        )

        return self._decrypt_note_for_response(note)

    async def unpin_note(self, note_id: UUID, user: User) -> Note:
        note = await self._note_repo.get_by_id(note_id)
        if not note:
            raise NotFoundError(f"Note {note_id} not found")
        if note.owner_id != user.id:
            raise InsufficientPermissionsError("Only the owner can unpin a note")
        if not note.is_pinned:
            raise ConflictError("Note is not pinned")

        note.is_pinned = False
        note.pinned_at = None
        await self._note_repo.save(note)

        await self._activity_repo.log(
            user_id=user.id, action_type=ActionType.NOTE_UNPINNED, note_id=note.id
        )

        return self._decrypt_note_for_response(note)

    # ── Version History ───────────────────────────────────────────────────────

    async def get_versions(self, note_id: UUID, user: User) -> list[NoteVersion]:
        note = await self._note_repo.get_by_id(note_id)
        if not note:
            raise NotFoundError(f"Note {note_id} not found")
        self._assert_can_read(note, user)
        return await self._note_repo.get_versions(note_id)

    async def get_version(self, note_id: UUID, version_number: int, user: User) -> NoteVersion:
        note = await self._note_repo.get_by_id(note_id)
        if not note:
            raise NotFoundError(f"Note {note_id} not found")
        await self._assert_can_read(note, user)

        version = await self._note_repo.get_version(note_id, version_number)
        if not version:
            raise NotFoundError(f"Version {version_number} not found")
        return version

    async def restore_version(self, note_id: UUID, version_number: int, user: User) -> Note:
        note = await self._note_repo.get_by_id(note_id)
        if not note:
            raise NotFoundError(f"Note {note_id} not found")
        if note.is_deleted:
            raise NoteDeletedError("Cannot restore a version on a deleted note")
        if note.owner_id != user.id:
            raise InsufficientPermissionsError("Only the owner can restore versions")

        version = await self._note_repo.get_version(note_id, version_number)
        if not version:
            raise NotFoundError(f"Version {version_number} not found")

        # Snapshot current state before restoring
        current_version_number = await self._note_repo.get_next_version_number(note_id)
        current_content = note.content
        if note.is_private:
            current_content = decrypt_content(note.content)

        snapshot = NoteVersion(
            note_id=note.id,
            version_number=current_version_number,
            title=note.title,
            content=current_content,
            modified_by_id=user.id,
        )
        self._session.add(snapshot)

        # Restore
        note.title = version.title
        if note.is_private:
            note.content, note.encryption_key_version = encrypt_content(version.content)
        else:
            note.content = version.content
        await self._note_repo.save(note)

        await self._activity_repo.log(
            user_id=user.id,
            action_type=ActionType.NOTE_VERSION_RESTORED,
            note_id=note.id,
            metadata={"restored_version": version_number, "snapshot_version": current_version_number},
        )

        return self._decrypt_note_for_response(note)

    # ── Share Links ───────────────────────────────────────────────────────────

    async def create_share_link(
        self, note_id: UUID, owner: User, data: ShareLinkCreateRequest
    ) -> tuple[ShareLink, str]:
        """Returns (ShareLink, raw_token). raw_token shown ONCE."""
        note = await self._note_repo.get_by_id(note_id)
        if not note:
            raise NotFoundError(f"Note {note_id} not found")
        if note.owner_id != owner.id:
            raise InsufficientPermissionsError("Only the owner can create share links")
        if note.is_deleted:
            raise NoteDeletedError("Cannot share a deleted note")

        raw_token, token_hash = generate_share_token()
        expiry_str = data.expiry if isinstance(data.expiry, str) else data.expiry.value
        delta = _EXPIRY_MAP[ShareLinkExpiry(expiry_str)]

        link = ShareLink(
            note_id=note.id,
            created_by_id=owner.id,
            token_hash=token_hash,
            expires_at=datetime.now(UTC) + delta,
            max_accesses=data.max_accesses,
        )
        self._session.add(link)
        await self._session.flush()
        await self._session.refresh(link)

        await self._activity_repo.log(
            user_id=owner.id,
            action_type=ActionType.NOTE_SHARE_LINK_CREATED,
            note_id=note.id,
            metadata={"expiry": expiry_str, "max_accesses": data.max_accesses},
        )

        return link, raw_token

    async def access_share_link(self, raw_token: str) -> Note:
        """Validates a share link and returns the note."""
        token_hash = hash_share_token(raw_token)
        link = await self._note_repo.get_share_link_by_hash(token_hash)

        if not link or not link.is_active:
            raise ShareTokenInvalidError("Share link is invalid or has been revoked")
        if link.is_expired:
            raise ShareTokenExpiredError("Share link has expired")
        if link.max_accesses and link.access_count >= link.max_accesses:
            raise ShareTokenInvalidError("Share link has reached its access limit")

        link.access_count += 1
        if link.max_accesses and link.access_count >= link.max_accesses:
            link.is_active = False  # deactivate one-time links
        await self._session.flush()

        await self._activity_repo.log(
            user_id=None,
            action_type=ActionType.NOTE_SHARE_LINK_ACCESSED,
            note_id=link.note_id,
            metadata={"access_count": link.access_count},
        )

        note = link.note
        if not note or note.is_deleted:
            raise NotFoundError("Note no longer available")

        return self._decrypt_note_for_response(note)

    # ── Helpers ───────────────────────────────────────────────────────────────

    async def _assert_can_read(self, note: Note, user: User) -> None:
        if note.owner_id == user.id:
            return
        
        # Check if shared with this user
        share = await self._note_repo.get_share(note.id, user.id)
        if share:
            return
            
        raise InsufficientPermissionsError("You do not have access to this note")

    async def _assert_can_write(self, note: Note, user: User) -> None:
        if note.owner_id == user.id:
            return
            
        # Check if shared with this user with WRITE permission
        share = await self._note_repo.get_share(note.id, user.id)
        if share and share.permission == NotePermission.WRITE:
            return
            
        raise InsufficientPermissionsError("You do not have write access to this note")

    def _decrypt_note_for_response(self, note: Note) -> Note:
        """
        Returns a note with decrypted content for the response.
        Operates on a shallow copy to avoid mutating the ORM object.
        """
        if note.is_private and note.encryption_key_version:
            # If it's already decrypted (e.g. if we're calling this on a non-ORM object 
            # or it was already processed), we skip to avoid Fernet errors.
            if hasattr(note, "_is_decrypted") and note._is_decrypted:
                return note

            # Expunge the note from the session so we don't accidentally save decrypted content
            if note in self._session:
                self._session.expunge(note)
            
            try:
                note.content = decrypt_content(note.content)
                note._is_decrypted = True # Mark as decrypted
            except Exception:
                note.content = "[Content unavailable — decryption failed]"
        return note
