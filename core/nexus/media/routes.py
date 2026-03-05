"""Media storage API routes."""

from uuid import UUID
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, UploadFile, File, Form, Query, status
from fastapi.responses import StreamingResponse, Response
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession

from nexus.auth import get_current_agent
from nexus.database import get_db
from nexus.identity.models import Agent
from nexus.media.service import MediaService
from nexus.media.models import MediaType, MediaStatus

router = APIRouter(prefix="/media", tags=["media"])


# --- File Security Validation ---

# Allowed MIME types and their magic bytes signatures
ALLOWED_TYPES = {
    # Images
    "image/jpeg": [b"\xff\xd8\xff"],
    "image/png": [b"\x89PNG\r\n\x1a\n"],
    "image/gif": [b"GIF87a", b"GIF89a"],
    "image/webp": [b"RIFF"],  # + "WEBP" at offset 8
    "image/svg+xml": [b"<?xml", b"<svg"],
    # Videos
    "video/mp4": [b"\x00\x00\x00\x18ftyp", b"\x00\x00\x00\x1cftyp", b"\x00\x00\x00\x20ftyp"],
    "video/webm": [b"\x1a\x45\xdf\xa3"],
    # Audio
    "audio/mpeg": [b"\xff\xfb", b"\xff\xfa", b"ID3"],
    "audio/wav": [b"RIFF"],
    "audio/ogg": [b"OggS"],
    # Documents
    "application/pdf": [b"%PDF"],
    "application/json": None,  # Text validation only
    "text/plain": None,
    "text/csv": None,
    "text/markdown": None,
}

# Dangerous file extensions that should never be allowed
BLOCKED_EXTENSIONS = {
    ".exe", ".dll", ".bat", ".cmd", ".sh", ".ps1", ".vbs",
    ".js", ".php", ".py", ".rb", ".pl", ".jar", ".war",
    ".msi", ".scr", ".pif", ".com", ".hta", ".cpl",
}


def validate_file_upload(filename: str, content: bytes, declared_type: str) -> str:
    """
    Validate file upload for security.
    Returns the validated content type or raises HTTPException.
    """
    import os

    # Check file extension
    _, ext = os.path.splitext(filename.lower())
    if ext in BLOCKED_EXTENSIONS:
        raise HTTPException(
            status_code=400,
            detail=f"File type '{ext}' is not allowed for security reasons"
        )

    # Validate against magic bytes if we have signatures
    if declared_type in ALLOWED_TYPES:
        signatures = ALLOWED_TYPES[declared_type]
        if signatures:
            # Check if file starts with any allowed signature
            matched = False
            for sig in signatures:
                if content[:len(sig)] == sig:
                    matched = True
                    break
            if not matched:
                raise HTTPException(
                    status_code=400,
                    detail=f"File content does not match declared type '{declared_type}'"
                )
        return declared_type

    # For unknown types, use generic binary type but block scripts
    # Check for script-like content at the start
    first_bytes = content[:1024].lower()
    dangerous_patterns = [
        b"<script", b"<?php", b"#!/", b"<%", b"import ", b"require(",
        b"eval(", b"exec(", b"system(",
    ]
    for pattern in dangerous_patterns:
        if pattern in first_bytes:
            raise HTTPException(
                status_code=400,
                detail="File appears to contain executable code"
            )

    return "application/octet-stream"


# --- Schemas ---

class MediaResponse(BaseModel):
    id: str
    filename: str
    content_type: str
    media_type: str
    size_bytes: int
    status: str
    is_public: bool
    download_url: str | None
    created_at: str


class ShareMediaRequest(BaseModel):
    agent_id: str
    can_download: bool = True
    can_reshare: bool = False
    expires_in_hours: int | None = None


# --- Routes ---

async def get_media_service(db: AsyncSession = Depends(get_db)) -> MediaService:
    return MediaService(db)


@router.post("", response_model=MediaResponse, status_code=status.HTTP_201_CREATED)
async def upload_media(
    file: Annotated[UploadFile, File(description="File to upload")],
    description: Annotated[str | None, Form()] = None,
    is_public: Annotated[bool, Form()] = False,
    expires_in_hours: Annotated[int | None, Form()] = None,
    agent: Agent = Depends(get_current_agent),
    service: MediaService = Depends(get_media_service),
):
    """
    Upload a media file (image, video, audio, document).

    Returns a media ID that can be passed to other agents.

    Security: Files are validated against magic bytes to prevent type spoofing.
    Executable files and scripts are blocked.
    """
    # Read file content
    content = await file.read()

    if len(content) > 500 * 1024 * 1024:  # 500MB limit
        raise HTTPException(status_code=413, detail="File too large (max 500MB)")

    if len(content) == 0:
        raise HTTPException(status_code=400, detail="Empty file not allowed")

    filename = file.filename or "unnamed"
    declared_type = file.content_type or "application/octet-stream"

    # Security validation: check magic bytes and block dangerous files
    validated_type = validate_file_upload(filename, content, declared_type)

    media = await service.upload(
        agent_id=agent.id,
        filename=filename,
        content_type=validated_type,
        data=content,
        description=description,
        is_public=is_public,
        expires_in_hours=expires_in_hours,
    )

    return _media_to_response(media, service)


@router.get("", response_model=list[MediaResponse])
async def list_media(
    media_type: str | None = Query(None, description="Filter by type: image, video, audio, document"),
    limit: int = Query(50, ge=1, le=100),
    offset: int = Query(0, ge=0),
    agent: Agent = Depends(get_current_agent),
    service: MediaService = Depends(get_media_service),
):
    """List my uploaded media files."""
    type_filter = None
    if media_type:
        try:
            type_filter = MediaType(media_type)
        except ValueError:
            raise HTTPException(status_code=400, detail=f"Invalid media type: {media_type}")

    files = await service.list_files(
        agent_id=agent.id,
        media_type=type_filter,
        limit=limit,
        offset=offset,
    )

    return [_media_to_response(f, service) for f in files]


@router.get("/shared")
async def get_shared_media(
    limit: int = Query(50, ge=1, le=100),
    agent: Agent = Depends(get_current_agent),
    service: MediaService = Depends(get_media_service),
):
    """Get media files shared with me."""
    return await service.get_shared_with_me(agent.id, limit=limit)


@router.get("/{media_id}", response_model=MediaResponse)
async def get_media(
    media_id: UUID,
    agent: Agent = Depends(get_current_agent),
    service: MediaService = Depends(get_media_service),
):
    """Get media file info."""
    if not await service.can_access(media_id, agent.id):
        raise HTTPException(status_code=404, detail="Media not found")

    media = await service.get(media_id)
    if not media:
        raise HTTPException(status_code=404, detail="Media not found")

    return _media_to_response(media, service)


@router.get("/{media_id}/download")
async def download_media(
    media_id: UUID,
    agent: Agent = Depends(get_current_agent),
    service: MediaService = Depends(get_media_service),
):
    """Download a media file."""
    result = await service.download(media_id, agent.id)
    if not result:
        raise HTTPException(status_code=404, detail="Media not found or access denied")

    data, media = result

    return Response(
        content=data,
        media_type=media.content_type,
        headers={
            "Content-Disposition": f'attachment; filename="{media.filename}"',
            "Content-Length": str(len(data)),
        },
    )


@router.get("/{media_id}/url")
async def get_download_url(
    media_id: UUID,
    expires_in: int = Query(3600, ge=60, le=86400, description="URL expiry in seconds"),
    agent: Agent = Depends(get_current_agent),
    service: MediaService = Depends(get_media_service),
):
    """Get a temporary download URL for direct access."""
    if not await service.can_access(media_id, agent.id):
        raise HTTPException(status_code=404, detail="Media not found")

    media = await service.get(media_id)
    if not media:
        raise HTTPException(status_code=404, detail="Media not found")

    url = service.get_download_url(media, expires_in=expires_in)
    return {
        "url": url,
        "expires_in": expires_in,
        "media_id": str(media_id),
    }


@router.delete("/{media_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_media(
    media_id: UUID,
    agent: Agent = Depends(get_current_agent),
    service: MediaService = Depends(get_media_service),
):
    """Delete a media file."""
    deleted = await service.delete(media_id, agent.id)
    if not deleted:
        raise HTTPException(status_code=404, detail="Media not found")


@router.post("/{media_id}/share")
async def share_media(
    media_id: UUID,
    data: ShareMediaRequest,
    agent: Agent = Depends(get_current_agent),
    service: MediaService = Depends(get_media_service),
):
    """Share a media file with another agent."""
    try:
        share = await service.share(
            media_id=media_id,
            owner_agent_id=agent.id,
            share_with_agent_id=UUID(data.agent_id),
            can_download=data.can_download,
            can_reshare=data.can_reshare,
            expires_in_hours=data.expires_in_hours,
        )
        return {
            "status": "shared",
            "share_id": str(share.id),
            "media_id": str(media_id),
            "shared_with": data.agent_id,
        }
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))


@router.delete("/{media_id}/share/{agent_id}", status_code=status.HTTP_204_NO_CONTENT)
async def unshare_media(
    media_id: UUID,
    agent_id: UUID,
    agent: Agent = Depends(get_current_agent),
    service: MediaService = Depends(get_media_service),
):
    """Remove sharing for a media file."""
    removed = await service.unshare(media_id, agent.id, agent_id)
    if not removed:
        raise HTTPException(status_code=404, detail="Share not found")


def _media_to_response(media, service: MediaService) -> MediaResponse:
    download_url = None
    if media.status == MediaStatus.READY:
        download_url = service.get_download_url(media, expires_in=3600)

    return MediaResponse(
        id=str(media.id),
        filename=media.filename,
        content_type=media.content_type,
        media_type=media.media_type.value,
        size_bytes=media.size_bytes,
        status=media.status.value,
        is_public=media.is_public,
        download_url=download_url,
        created_at=media.created_at.isoformat(),
    )
