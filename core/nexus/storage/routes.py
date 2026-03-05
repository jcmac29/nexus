"""File storage API routes."""

from __future__ import annotations

from uuid import UUID
from fastapi import APIRouter, Depends, HTTPException, UploadFile, File, Query
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession

from nexus.database import get_db
from nexus.auth import get_current_agent
from nexus.identity.models import Agent
from nexus.storage.service import StorageService

router = APIRouter(prefix="/storage", tags=["storage"])


class PresignedUploadRequest(BaseModel):
    filename: str
    content_type: str | None = None
    bucket: str | None = None


class ConfirmUploadRequest(BaseModel):
    size_bytes: int | None = None
    checksum: str | None = None


class CopyFileRequest(BaseModel):
    new_owner_id: str | None = None
    new_bucket: str | None = None


@router.post("/upload")
async def upload_file(
    file: UploadFile = File(...),
    is_public: bool = False,
    bucket: str | None = None,
    entity_type: str | None = None,
    entity_id: str | None = None,
    agent: Agent = Depends(get_current_agent),
    db: AsyncSession = Depends(get_db),
):
    """Upload a file directly."""
    service = StorageService(db)

    contents = await file.read()
    stored_file = await service.upload_file(
        file_data=contents,
        filename=file.filename or "unnamed",
        owner_id=agent.id,
        bucket=bucket,
        content_type=file.content_type,
        is_public=is_public,
        entity_type=entity_type,
        entity_id=UUID(entity_id) if entity_id else None,
    )

    return {
        "id": str(stored_file.id),
        "key": stored_file.key,
        "filename": stored_file.original_filename,
        "size_bytes": stored_file.size_bytes,
        "content_type": stored_file.content_type,
        "url": stored_file.url,
        "status": stored_file.status.value,
    }


@router.post("/presigned-upload")
async def get_presigned_upload(
    request: PresignedUploadRequest,
    agent: Agent = Depends(get_current_agent),
    db: AsyncSession = Depends(get_db),
):
    """Get a presigned URL for direct upload to S3."""
    service = StorageService(db)

    url, key, file_id = await service.get_presigned_upload_url(
        filename=request.filename,
        owner_id=agent.id,
        bucket=request.bucket,
        content_type=request.content_type,
    )

    return {
        "upload_url": url,
        "key": key,
        "file_id": str(file_id),
    }


@router.post("/{file_id}/confirm")
async def confirm_upload(
    file_id: str,
    request: ConfirmUploadRequest,
    agent: Agent = Depends(get_current_agent),
    db: AsyncSession = Depends(get_db),
):
    """Confirm a presigned upload completed."""
    service = StorageService(db)
    await service.confirm_upload(
        file_id=UUID(file_id),
        size_bytes=request.size_bytes,
        checksum=request.checksum,
    )
    return {"status": "confirmed"}


@router.get("/")
async def list_files(
    bucket: str | None = None,
    entity_type: str | None = None,
    entity_id: str | None = None,
    limit: int = Query(default=100, le=500),
    agent: Agent = Depends(get_current_agent),
    db: AsyncSession = Depends(get_db),
):
    """List files."""
    service = StorageService(db)
    files = await service.list_files(
        owner_id=agent.id,
        bucket=bucket,
        entity_type=entity_type,
        entity_id=UUID(entity_id) if entity_id else None,
        limit=limit,
    )

    return [
        {
            "id": str(f.id),
            "key": f.key,
            "filename": f.original_filename,
            "size_bytes": f.size_bytes,
            "content_type": f.content_type,
            "url": f.url,
            "is_public": f.is_public,
            "created_at": f.created_at.isoformat(),
        }
        for f in files
    ]


@router.get("/{file_id}")
async def get_file(
    file_id: str,
    agent: Agent = Depends(get_current_agent),
    db: AsyncSession = Depends(get_db),
):
    """Get file metadata."""
    service = StorageService(db)
    stored_file = await service.get_file(UUID(file_id))
    if not stored_file:
        raise HTTPException(status_code=404, detail="File not found")

    return {
        "id": str(stored_file.id),
        "key": stored_file.key,
        "bucket": stored_file.bucket,
        "filename": stored_file.original_filename,
        "size_bytes": stored_file.size_bytes,
        "content_type": stored_file.content_type,
        "checksum": stored_file.checksum,
        "url": stored_file.url,
        "is_public": stored_file.is_public,
        "status": stored_file.status.value,
        "metadata": stored_file.metadata,
        "created_at": stored_file.created_at.isoformat(),
    }


@router.get("/{file_id}/download-url")
async def get_download_url(
    file_id: str,
    expires_in: int = Query(default=3600, le=86400),
    agent: Agent = Depends(get_current_agent),
    db: AsyncSession = Depends(get_db),
):
    """Get a presigned download URL."""
    service = StorageService(db)

    # SECURITY: Verify ownership or public access before generating URL
    file = await service.get_file(UUID(file_id))
    if not file:
        raise HTTPException(status_code=404, detail="File not found")
    if file.owner_id != agent.id and not file.is_public:
        raise HTTPException(status_code=403, detail="Not authorized to access this file")

    url = await service.get_presigned_url(UUID(file_id), expires_in=expires_in)
    return {"url": url, "expires_in": expires_in}


@router.post("/{file_id}/copy")
async def copy_file(
    file_id: str,
    request: CopyFileRequest,
    agent: Agent = Depends(get_current_agent),
    db: AsyncSession = Depends(get_db),
):
    """Copy a file."""
    service = StorageService(db)

    # SECURITY: Verify ownership or public access before copying
    file = await service.get_file(UUID(file_id))
    if not file:
        raise HTTPException(status_code=404, detail="File not found")
    if file.owner_id != agent.id and not file.is_public:
        raise HTTPException(status_code=403, detail="Not authorized to copy this file")

    new_file = await service.copy_file(
        file_id=UUID(file_id),
        new_owner_id=UUID(request.new_owner_id) if request.new_owner_id else agent.id,
        new_bucket=request.new_bucket,
    )

    return {
        "id": str(new_file.id),
        "key": new_file.key,
        "filename": new_file.original_filename,
    }


@router.delete("/{file_id}")
async def delete_file(
    file_id: str,
    permanent: bool = False,
    agent: Agent = Depends(get_current_agent),
    db: AsyncSession = Depends(get_db),
):
    """Delete a file."""
    service = StorageService(db)

    # SECURITY: Verify ownership before deletion
    file = await service.get_file(UUID(file_id))
    if not file:
        raise HTTPException(status_code=404, detail="File not found")
    if file.owner_id != agent.id:
        raise HTTPException(status_code=403, detail="Not authorized to delete this file")

    await service.delete_file(UUID(file_id), soft=not permanent)
    return {"status": "deleted"}


@router.get("/stats/usage")
async def get_storage_stats(
    agent: Agent = Depends(get_current_agent),
    db: AsyncSession = Depends(get_db),
):
    """Get storage usage statistics."""
    service = StorageService(db)
    stats = await service.get_storage_stats(agent.id)
    return stats
