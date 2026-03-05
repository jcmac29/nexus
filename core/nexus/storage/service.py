"""File storage service with S3-compatible backends."""

from __future__ import annotations

import hashlib
import mimetypes
import os
import re
from datetime import datetime, timedelta
from uuid import UUID
import uuid as uuid_module
from pathlib import Path

from sqlalchemy import select, and_
from sqlalchemy.ext.asyncio import AsyncSession

from nexus.storage.models import StoredFile, StorageBucket, StorageProvider, FileStatus


def _validate_bucket_name(bucket: str) -> str:
    """
    Validate and sanitize bucket name to prevent path traversal.

    SECURITY: Only allow alphanumeric characters, hyphens, and underscores.
    """
    if not bucket:
        raise ValueError("Bucket name cannot be empty")

    # Remove any path traversal attempts
    sanitized = re.sub(r'[^a-zA-Z0-9_-]', '', bucket)

    if not sanitized:
        raise ValueError("Invalid bucket name")

    # Ensure it doesn't start with a dash
    sanitized = sanitized.lstrip('-')

    if len(sanitized) > 63:
        sanitized = sanitized[:63]

    return sanitized


def _safe_path_join(base: Path, *parts: str) -> Path:
    """
    Safely join paths and verify result is within base directory.

    SECURITY: Prevents path traversal attacks.
    """
    result = base
    for part in parts:
        # Sanitize each part
        part = part.replace('..', '').replace('/', '').replace('\\', '')
        result = result / part

    # Resolve and verify path is within base
    resolved = result.resolve()
    base_resolved = base.resolve()

    if not str(resolved).startswith(str(base_resolved)):
        raise ValueError("Path traversal detected")

    return resolved


class StorageService:
    """Service for file storage operations."""

    def __init__(self, db: AsyncSession):
        self.db = db
        self._s3_client = None
        self._default_bucket = "nexus-files"
        self._local_path = "/tmp/nexus-storage"

    def configure_s3(
        self,
        access_key: str,
        secret_key: str,
        region: str = "us-east-1",
        endpoint: str | None = None,
    ):
        """Configure S3 or S3-compatible storage."""
        import boto3
        config = {
            "aws_access_key_id": access_key,
            "aws_secret_access_key": secret_key,
            "region_name": region,
        }
        if endpoint:
            config["endpoint_url"] = endpoint

        self._s3_client = boto3.client("s3", **config)

    def configure_local(self, path: str = "/tmp/nexus-storage"):
        """Configure local file storage."""
        self._local_path = path
        os.makedirs(path, exist_ok=True)

    async def upload_file(
        self,
        file_data: bytes,
        filename: str,
        owner_id: UUID,
        bucket: str | None = None,
        content_type: str | None = None,
        is_public: bool = False,
        metadata: dict | None = None,
        entity_type: str | None = None,
        entity_id: UUID | None = None,
    ) -> StoredFile:
        """Upload a file."""
        # SECURITY: Validate and sanitize bucket name
        bucket = _validate_bucket_name(bucket or self._default_bucket)

        # Generate unique key
        file_id = str(uuid_module.uuid4())
        ext = Path(filename).suffix
        key = f"{owner_id}/{file_id}{ext}"

        # Detect content type
        if not content_type:
            content_type, _ = mimetypes.guess_type(filename)
            content_type = content_type or "application/octet-stream"

        # Calculate checksum
        checksum = hashlib.sha256(file_data).hexdigest()

        # Upload to backend
        url = None
        if self._s3_client:
            try:
                extra_args = {"ContentType": content_type}
                if is_public:
                    extra_args["ACL"] = "public-read"
                if metadata:
                    extra_args["Metadata"] = {k: str(v) for k, v in metadata.items()}

                self._s3_client.put_object(
                    Bucket=bucket,
                    Key=key,
                    Body=file_data,
                    **extra_args,
                )

                if is_public:
                    # Construct public URL
                    url = f"https://{bucket}.s3.amazonaws.com/{key}"
            except Exception as e:
                raise RuntimeError(f"Failed to upload to S3: {e}")
        else:
            # Local storage - SECURITY: Use safe path join to prevent traversal
            base_path = Path(self._local_path)
            file_path = _safe_path_join(base_path, bucket, key)
            file_path.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
            file_path.write_bytes(file_data)
            url = f"file://{file_path}"

        # Create database record
        stored_file = StoredFile(
            key=key,
            bucket=bucket,
            original_filename=filename,
            provider=StorageProvider.S3 if self._s3_client else StorageProvider.LOCAL,
            owner_id=owner_id,
            content_type=content_type,
            size_bytes=len(file_data),
            checksum=checksum,
            status=FileStatus.READY,
            url=url,
            is_public=is_public,
            metadata=metadata or {},
            entity_type=entity_type,
            entity_id=entity_id,
        )
        self.db.add(stored_file)
        await self.db.commit()
        await self.db.refresh(stored_file)
        return stored_file

    async def upload_from_path(
        self,
        file_path: str,
        owner_id: UUID,
        **kwargs,
    ) -> StoredFile:
        """Upload a file from a local path."""
        path = Path(file_path)
        file_data = path.read_bytes()
        filename = path.name
        return await self.upload_file(file_data, filename, owner_id, **kwargs)

    async def download_file(self, file_id: UUID) -> tuple[bytes, str, str]:
        """Download a file. Returns (data, filename, content_type)."""
        result = await self.db.execute(
            select(StoredFile).where(StoredFile.id == file_id)
        )
        stored_file = result.scalar_one_or_none()
        if not stored_file:
            raise ValueError("File not found")

        if self._s3_client:
            response = self._s3_client.get_object(
                Bucket=stored_file.bucket,
                Key=stored_file.key,
            )
            data = response["Body"].read()
        else:
            # SECURITY: Use safe path join to prevent path traversal attacks
            base_path = Path(self._local_path)
            file_path = _safe_path_join(base_path, stored_file.bucket, stored_file.key)
            data = file_path.read_bytes()

        return data, stored_file.original_filename or stored_file.key, stored_file.content_type

    async def get_presigned_url(
        self,
        file_id: UUID,
        expires_in: int = 3600,
        operation: str = "get",
    ) -> str:
        """Get a presigned URL for file access."""
        result = await self.db.execute(
            select(StoredFile).where(StoredFile.id == file_id)
        )
        stored_file = result.scalar_one_or_none()
        if not stored_file:
            raise ValueError("File not found")

        if self._s3_client:
            client_method = "get_object" if operation == "get" else "put_object"
            url = self._s3_client.generate_presigned_url(
                ClientMethod=client_method,
                Params={"Bucket": stored_file.bucket, "Key": stored_file.key},
                ExpiresIn=expires_in,
            )
            return url
        else:
            # For local storage, return the file path
            return stored_file.url or f"file://{self._local_path}/{stored_file.bucket}/{stored_file.key}"

    async def get_presigned_upload_url(
        self,
        filename: str,
        owner_id: UUID,
        bucket: str | None = None,
        content_type: str | None = None,
        expires_in: int = 3600,
    ) -> tuple[str, str, UUID]:
        """
        Get a presigned URL for direct upload.
        Returns (upload_url, key, file_id).
        """
        bucket = bucket or self._default_bucket

        # Generate unique key
        file_id = uuid_module.uuid4()
        ext = Path(filename).suffix
        key = f"{owner_id}/{file_id}{ext}"

        if not content_type:
            content_type, _ = mimetypes.guess_type(filename)
            content_type = content_type or "application/octet-stream"

        # Create pending file record
        stored_file = StoredFile(
            id=file_id,
            key=key,
            bucket=bucket,
            original_filename=filename,
            provider=StorageProvider.S3 if self._s3_client else StorageProvider.LOCAL,
            owner_id=owner_id,
            content_type=content_type,
            status=FileStatus.UPLOADING,
        )
        self.db.add(stored_file)
        await self.db.commit()

        if self._s3_client:
            url = self._s3_client.generate_presigned_url(
                ClientMethod="put_object",
                Params={
                    "Bucket": bucket,
                    "Key": key,
                    "ContentType": content_type,
                },
                ExpiresIn=expires_in,
            )
            return url, key, file_id
        else:
            # For local storage
            return f"file://{self._local_path}/{bucket}/{key}", key, file_id

    async def confirm_upload(
        self,
        file_id: UUID,
        size_bytes: int | None = None,
        checksum: str | None = None,
    ):
        """Confirm that a presigned upload completed."""
        result = await self.db.execute(
            select(StoredFile).where(StoredFile.id == file_id)
        )
        stored_file = result.scalar_one_or_none()
        if not stored_file:
            raise ValueError("File not found")

        stored_file.status = FileStatus.READY
        if size_bytes:
            stored_file.size_bytes = size_bytes
        if checksum:
            stored_file.checksum = checksum

        # Get actual size from storage if not provided
        if not size_bytes and self._s3_client:
            try:
                head = self._s3_client.head_object(
                    Bucket=stored_file.bucket,
                    Key=stored_file.key,
                )
                stored_file.size_bytes = head.get("ContentLength")
            except Exception:
                pass

        await self.db.commit()

    async def delete_file(self, file_id: UUID, soft: bool = True):
        """Delete a file."""
        result = await self.db.execute(
            select(StoredFile).where(StoredFile.id == file_id)
        )
        stored_file = result.scalar_one_or_none()
        if not stored_file:
            return

        if soft:
            stored_file.status = FileStatus.DELETED
            stored_file.deleted_at = datetime.utcnow()
        else:
            # Actually delete from storage
            if self._s3_client:
                self._s3_client.delete_object(
                    Bucket=stored_file.bucket,
                    Key=stored_file.key,
                )
            else:
                file_path = Path(self._local_path) / stored_file.bucket / stored_file.key
                if file_path.exists():
                    file_path.unlink()

            await self.db.delete(stored_file)

        await self.db.commit()

    async def copy_file(
        self,
        file_id: UUID,
        new_owner_id: UUID | None = None,
        new_bucket: str | None = None,
    ) -> StoredFile:
        """Copy a file."""
        result = await self.db.execute(
            select(StoredFile).where(StoredFile.id == file_id)
        )
        source_file = result.scalar_one_or_none()
        if not source_file:
            raise ValueError("File not found")

        new_id = uuid_module.uuid4()
        new_owner = new_owner_id or source_file.owner_id
        new_bucket = new_bucket or source_file.bucket

        ext = Path(source_file.key).suffix
        new_key = f"{new_owner}/{new_id}{ext}"

        if self._s3_client:
            self._s3_client.copy_object(
                CopySource={"Bucket": source_file.bucket, "Key": source_file.key},
                Bucket=new_bucket,
                Key=new_key,
            )
        else:
            source_path = Path(self._local_path) / source_file.bucket / source_file.key
            dest_path = Path(self._local_path) / new_bucket / new_key
            dest_path.parent.mkdir(parents=True, exist_ok=True)
            dest_path.write_bytes(source_path.read_bytes())

        new_file = StoredFile(
            id=new_id,
            key=new_key,
            bucket=new_bucket,
            original_filename=source_file.original_filename,
            provider=source_file.provider,
            owner_id=new_owner,
            content_type=source_file.content_type,
            size_bytes=source_file.size_bytes,
            checksum=source_file.checksum,
            status=FileStatus.READY,
            is_public=source_file.is_public,
            metadata=source_file.metadata.copy(),
        )
        self.db.add(new_file)
        await self.db.commit()
        await self.db.refresh(new_file)
        return new_file

    async def list_files(
        self,
        owner_id: UUID,
        bucket: str | None = None,
        entity_type: str | None = None,
        entity_id: UUID | None = None,
        limit: int = 100,
    ) -> list[StoredFile]:
        """List files for an owner."""
        query = select(StoredFile).where(
            and_(
                StoredFile.owner_id == owner_id,
                StoredFile.status == FileStatus.READY,
            )
        )
        if bucket:
            query = query.where(StoredFile.bucket == bucket)
        if entity_type:
            query = query.where(StoredFile.entity_type == entity_type)
        if entity_id:
            query = query.where(StoredFile.entity_id == entity_id)

        query = query.order_by(StoredFile.created_at.desc()).limit(limit)

        result = await self.db.execute(query)
        return list(result.scalars().all())

    async def get_file(self, file_id: UUID) -> StoredFile | None:
        """Get file metadata."""
        result = await self.db.execute(
            select(StoredFile).where(StoredFile.id == file_id)
        )
        return result.scalar_one_or_none()

    async def get_storage_stats(self, owner_id: UUID) -> dict:
        """Get storage statistics for an owner."""
        from sqlalchemy import func

        result = await self.db.execute(
            select(
                func.count(StoredFile.id),
                func.coalesce(func.sum(StoredFile.size_bytes), 0),
            )
            .where(
                and_(
                    StoredFile.owner_id == owner_id,
                    StoredFile.status == FileStatus.READY,
                )
            )
        )
        row = result.one()

        return {
            "file_count": row[0],
            "total_size_bytes": row[1],
            "total_size_mb": round(row[1] / (1024 * 1024), 2),
        }
