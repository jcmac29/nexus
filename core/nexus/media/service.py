"""Media storage service."""

import json
from datetime import datetime, timezone, timedelta
from uuid import UUID
from typing import Any, BinaryIO

from sqlalchemy import select, or_
from sqlalchemy.ext.asyncio import AsyncSession

from nexus.media.models import MediaFile, MediaShare, MediaType, MediaStatus
from nexus.media.storage import get_storage


def detect_media_type(content_type: str) -> MediaType:
    """Detect media type from MIME type."""
    if content_type.startswith("image/"):
        return MediaType.IMAGE
    elif content_type.startswith("video/"):
        return MediaType.VIDEO
    elif content_type.startswith("audio/"):
        return MediaType.AUDIO
    elif content_type in [
        "application/pdf",
        "application/msword",
        "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
        "text/plain",
        "text/csv",
    ]:
        return MediaType.DOCUMENT
    return MediaType.OTHER


class MediaService:
    """Service for managing media files."""

    def __init__(self, db: AsyncSession):
        self.db = db
        self.storage = get_storage()

    async def upload(
        self,
        agent_id: UUID,
        filename: str,
        content_type: str,
        data: bytes | BinaryIO,
        description: str | None = None,
        is_public: bool = False,
        expires_in_hours: int | None = None,
        metadata: dict | None = None,
    ) -> MediaFile:
        """Upload a media file."""
        # Generate storage key
        storage_key = self.storage.generate_key(str(agent_id), filename)

        # Determine size
        if isinstance(data, bytes):
            size = len(data)
        else:
            # Get size from stream
            data.seek(0, 2)  # Seek to end
            size = data.tell()
            data.seek(0)  # Seek back to start

        # Create DB record first
        media = MediaFile(
            agent_id=agent_id,
            filename=filename,
            content_type=content_type,
            media_type=detect_media_type(content_type),
            size_bytes=size,
            storage_key=storage_key,
            storage_bucket=self.storage.bucket,
            status=MediaStatus.UPLOADING,
            description=description,
            is_public=is_public,
            metadata_=json.dumps(metadata) if metadata else None,
            expires_at=(
                datetime.now(timezone.utc) + timedelta(hours=expires_in_hours)
                if expires_in_hours else None
            ),
        )
        self.db.add(media)
        await self.db.flush()

        try:
            # Upload to storage
            if isinstance(data, bytes):
                self.storage.upload_bytes(storage_key, data, content_type)
            else:
                self.storage.upload_file(storage_key, data, content_type, size)

            # Mark as ready
            media.status = MediaStatus.READY

        except Exception as e:
            media.status = MediaStatus.FAILED
            raise

        return media

    async def get(self, media_id: UUID) -> MediaFile | None:
        """Get a media file by ID."""
        result = await self.db.execute(
            select(MediaFile).where(
                MediaFile.id == media_id,
                MediaFile.status != MediaStatus.DELETED,
            )
        )
        return result.scalar_one_or_none()

    async def get_by_key(self, storage_key: str) -> MediaFile | None:
        """Get a media file by storage key."""
        result = await self.db.execute(
            select(MediaFile).where(
                MediaFile.storage_key == storage_key,
                MediaFile.status != MediaStatus.DELETED,
            )
        )
        return result.scalar_one_or_none()

    async def can_access(self, media_id: UUID, agent_id: UUID) -> bool:
        """Check if an agent can access a media file."""
        media = await self.get(media_id)
        if not media:
            return False

        # Owner can always access
        if media.agent_id == agent_id:
            return True

        # Public files are accessible
        if media.is_public:
            return True

        # Check for explicit share
        result = await self.db.execute(
            select(MediaShare).where(
                MediaShare.media_id == media_id,
                MediaShare.shared_with_agent_id == agent_id,
            )
        )
        share = result.scalar_one_or_none()
        if share:
            # Check expiry
            if share.expires_at and share.expires_at < datetime.now(timezone.utc):
                return False
            return True

        return False

    async def download(self, media_id: UUID, agent_id: UUID) -> tuple[bytes, MediaFile] | None:
        """Download a media file."""
        if not await self.can_access(media_id, agent_id):
            return None

        media = await self.get(media_id)
        if not media or media.status != MediaStatus.READY:
            return None

        data = self.storage.download_file(media.storage_key)
        return data, media

    def get_download_url(self, media: MediaFile, expires_in: int = 3600) -> str:
        """Get a presigned download URL."""
        return self.storage.generate_presigned_url(
            media.storage_key,
            expires_in=expires_in,
        )

    async def delete(self, media_id: UUID, agent_id: UUID) -> bool:
        """Delete a media file."""
        media = await self.get(media_id)
        if not media or media.agent_id != agent_id:
            return False

        # Delete from storage
        self.storage.delete_file(media.storage_key)

        # Mark as deleted in DB
        media.status = MediaStatus.DELETED
        return True

    async def list_files(
        self,
        agent_id: UUID,
        media_type: MediaType | None = None,
        limit: int = 50,
        offset: int = 0,
    ) -> list[MediaFile]:
        """List media files for an agent."""
        query = (
            select(MediaFile)
            .where(
                MediaFile.agent_id == agent_id,
                MediaFile.status == MediaStatus.READY,
            )
        )

        if media_type:
            query = query.where(MediaFile.media_type == media_type)

        query = (
            query
            .order_by(MediaFile.created_at.desc())
            .offset(offset)
            .limit(limit)
        )

        result = await self.db.execute(query)
        return list(result.scalars().all())

    async def share(
        self,
        media_id: UUID,
        owner_agent_id: UUID,
        share_with_agent_id: UUID,
        can_download: bool = True,
        can_reshare: bool = False,
        expires_in_hours: int | None = None,
    ) -> MediaShare:
        """Share a media file with another agent."""
        media = await self.get(media_id)
        if not media or media.agent_id != owner_agent_id:
            raise ValueError("Media not found or not owned by agent")

        # Check if already shared
        result = await self.db.execute(
            select(MediaShare).where(
                MediaShare.media_id == media_id,
                MediaShare.shared_with_agent_id == share_with_agent_id,
            )
        )
        existing = result.scalar_one_or_none()
        if existing:
            return existing

        share = MediaShare(
            media_id=media_id,
            shared_with_agent_id=share_with_agent_id,
            shared_by_agent_id=owner_agent_id,
            can_download=can_download,
            can_reshare=can_reshare,
            expires_at=(
                datetime.now(timezone.utc) + timedelta(hours=expires_in_hours)
                if expires_in_hours else None
            ),
        )
        self.db.add(share)
        await self.db.flush()
        return share

    async def unshare(
        self,
        media_id: UUID,
        owner_agent_id: UUID,
        shared_with_agent_id: UUID,
    ) -> bool:
        """Remove sharing for a media file."""
        media = await self.get(media_id)
        if not media or media.agent_id != owner_agent_id:
            return False

        result = await self.db.execute(
            select(MediaShare).where(
                MediaShare.media_id == media_id,
                MediaShare.shared_with_agent_id == shared_with_agent_id,
            )
        )
        share = result.scalar_one_or_none()
        if share:
            await self.db.delete(share)
            return True
        return False

    async def get_shared_with_me(
        self,
        agent_id: UUID,
        limit: int = 50,
    ) -> list[dict[str, Any]]:
        """Get media files shared with an agent."""
        now = datetime.now(timezone.utc)
        result = await self.db.execute(
            select(MediaShare, MediaFile)
            .join(MediaFile, MediaShare.media_id == MediaFile.id)
            .where(
                MediaShare.shared_with_agent_id == agent_id,
                MediaFile.status == MediaStatus.READY,
                or_(
                    MediaShare.expires_at.is_(None),
                    MediaShare.expires_at > now,
                ),
            )
            .order_by(MediaShare.created_at.desc())
            .limit(limit)
        )

        return [
            {
                "media_id": str(media.id),
                "filename": media.filename,
                "content_type": media.content_type,
                "media_type": media.media_type.value,
                "size_bytes": media.size_bytes,
                "shared_by": str(share.shared_by_agent_id),
                "can_download": share.can_download,
                "shared_at": share.created_at.isoformat(),
            }
            for share, media in result.all()
        ]

    async def cleanup_expired(self) -> int:
        """Delete expired media files."""
        now = datetime.now(timezone.utc)
        result = await self.db.execute(
            select(MediaFile).where(
                MediaFile.expires_at < now,
                MediaFile.status == MediaStatus.READY,
            )
        )

        count = 0
        for media in result.scalars().all():
            self.storage.delete_file(media.storage_key)
            media.status = MediaStatus.DELETED
            count += 1

        return count
