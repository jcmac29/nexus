"""Documents API routes."""

from __future__ import annotations

from datetime import datetime
from uuid import UUID
from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession

from nexus.database import get_db
from nexus.auth import get_current_agent
from nexus.identity.models import Agent
from nexus.documents.service import DocumentService
from nexus.documents.models import DocumentType, PermissionLevel

router = APIRouter(prefix="/documents", tags=["documents"])


class CreateDocumentRequest(BaseModel):
    title: str
    document_type: str = "text"
    content: str | None = None
    folder_id: str | None = None
    is_public: bool = False
    tags: list[str] | None = None
    ai_agent_id: str | None = None


class UpdateDocumentRequest(BaseModel):
    title: str | None = None
    content: str | None = None
    tags: list[str] | None = None
    change_summary: str | None = None


class ShareDocumentRequest(BaseModel):
    grantee_id: str | None = None
    grantee_email: str | None = None
    permission: str = "viewer"
    expires_at: str | None = None


class AddCommentRequest(BaseModel):
    content: str
    parent_id: str | None = None
    anchor_type: str | None = None
    anchor_data: dict | None = None
    is_suggestion: bool = False
    suggested_content: str | None = None


class CreateFolderRequest(BaseModel):
    name: str
    parent_id: str | None = None


@router.post("/")
async def create_document(
    request: CreateDocumentRequest,
    agent: Agent = Depends(get_current_agent),
    db: AsyncSession = Depends(get_db),
):
    """Create a new document."""
    service = DocumentService(db)

    type_map = {
        "text": DocumentType.TEXT,
        "markdown": DocumentType.MARKDOWN,
        "code": DocumentType.CODE,
        "spreadsheet": DocumentType.SPREADSHEET,
        "presentation": DocumentType.PRESENTATION,
        "whiteboard": DocumentType.WHITEBOARD,
    }

    doc = await service.create_document(
        title=request.title,
        owner_id=agent.id,
        document_type=type_map.get(request.document_type, DocumentType.TEXT),
        content=request.content,
        folder_id=UUID(request.folder_id) if request.folder_id else None,
        is_public=request.is_public,
        tags=request.tags,
        ai_agent_id=UUID(request.ai_agent_id) if request.ai_agent_id else None,
    )

    return {
        "id": str(doc.id),
        "title": doc.title,
        "document_type": doc.document_type.value,
        "version": doc.version,
        "public_link_id": doc.public_link_id,
    }


@router.get("/")
async def list_documents(
    folder_id: str | None = None,
    document_type: str | None = None,
    include_shared: bool = True,
    include_trashed: bool = False,
    limit: int = Query(default=50, le=100),
    agent: Agent = Depends(get_current_agent),
    db: AsyncSession = Depends(get_db),
):
    """List documents."""
    service = DocumentService(db)

    type_map = {
        "text": DocumentType.TEXT,
        "markdown": DocumentType.MARKDOWN,
        "code": DocumentType.CODE,
    }

    docs = await service.list_documents(
        owner_id=agent.id,
        folder_id=UUID(folder_id) if folder_id else None,
        document_type=type_map.get(document_type) if document_type else None,
        include_shared=include_shared,
        include_trashed=include_trashed,
        limit=limit,
    )

    return [
        {
            "id": str(d.id),
            "title": d.title,
            "document_type": d.document_type.value,
            "version": d.version,
            "is_public": d.is_public,
            "word_count": d.word_count,
            "updated_at": d.updated_at.isoformat(),
        }
        for d in docs
    ]


@router.get("/search")
async def search_documents(
    q: str,
    limit: int = Query(default=20, le=50),
    agent: Agent = Depends(get_current_agent),
    db: AsyncSession = Depends(get_db),
):
    """Search documents."""
    service = DocumentService(db)
    docs = await service.search_documents(agent.id, q, limit)

    return [
        {
            "id": str(d.id),
            "title": d.title,
            "document_type": d.document_type.value,
            "updated_at": d.updated_at.isoformat(),
        }
        for d in docs
    ]


@router.get("/{document_id}")
async def get_document(
    document_id: str,
    agent: Agent = Depends(get_current_agent),
    db: AsyncSession = Depends(get_db),
):
    """Get a document."""
    service = DocumentService(db)

    # Check permission
    has_access = await service.check_permission(
        UUID(document_id), agent.id, PermissionLevel.VIEWER
    )
    if not has_access:
        raise HTTPException(status_code=403, detail="Access denied")

    doc = await service.get_document(UUID(document_id), agent.id)
    if not doc:
        raise HTTPException(status_code=404, detail="Document not found")

    return {
        "id": str(doc.id),
        "title": doc.title,
        "document_type": doc.document_type.value,
        "content": doc.content,
        "version": doc.version,
        "tags": doc.tags,
        "is_public": doc.is_public,
        "word_count": doc.word_count,
        "ai_summary": doc.ai_summary,
        "created_at": doc.created_at.isoformat(),
        "updated_at": doc.updated_at.isoformat(),
    }


@router.patch("/{document_id}")
async def update_document(
    document_id: str,
    request: UpdateDocumentRequest,
    agent: Agent = Depends(get_current_agent),
    db: AsyncSession = Depends(get_db),
):
    """Update a document."""
    service = DocumentService(db)

    # Check permission
    has_access = await service.check_permission(
        UUID(document_id), agent.id, PermissionLevel.EDITOR
    )
    if not has_access:
        raise HTTPException(status_code=403, detail="Edit access denied")

    doc = await service.update_document(
        document_id=UUID(document_id),
        editor_id=agent.id,
        content=request.content,
        title=request.title,
        tags=request.tags,
        change_summary=request.change_summary,
    )

    return {
        "id": str(doc.id),
        "title": doc.title,
        "version": doc.version,
        "updated_at": doc.updated_at.isoformat(),
    }


@router.delete("/{document_id}")
async def delete_document(
    document_id: str,
    permanent: bool = False,
    agent: Agent = Depends(get_current_agent),
    db: AsyncSession = Depends(get_db),
):
    """Delete a document."""
    service = DocumentService(db)

    # SECURITY: Check owner permission before deletion
    has_access = await service.check_permission(
        UUID(document_id), agent.id, PermissionLevel.OWNER
    )
    if not has_access:
        raise HTTPException(status_code=403, detail="Delete access denied - owner permission required")

    await service.delete_document(UUID(document_id), soft=not permanent)
    return {"status": "deleted" if permanent else "trashed"}


@router.post("/{document_id}/share")
async def share_document(
    document_id: str,
    request: ShareDocumentRequest,
    agent: Agent = Depends(get_current_agent),
    db: AsyncSession = Depends(get_db),
):
    """Share a document."""
    service = DocumentService(db)

    # SECURITY: Check owner permission before sharing
    has_access = await service.check_permission(
        UUID(document_id), agent.id, PermissionLevel.OWNER
    )
    if not has_access:
        raise HTTPException(status_code=403, detail="Only owners can share documents")

    permission_map = {
        "owner": PermissionLevel.OWNER,
        "editor": PermissionLevel.EDITOR,
        "commenter": PermissionLevel.COMMENTER,
        "viewer": PermissionLevel.VIEWER,
    }

    perm = await service.share_document(
        document_id=UUID(document_id),
        grantee_id=UUID(request.grantee_id) if request.grantee_id else None,
        grantee_email=request.grantee_email,
        permission=permission_map.get(request.permission, PermissionLevel.VIEWER),
        invited_by_id=agent.id,
        expires_at=datetime.fromisoformat(request.expires_at) if request.expires_at else None,
    )

    return {
        "id": str(perm.id),
        "permission": perm.permission.value,
    }


@router.get("/{document_id}/versions")
async def get_versions(
    document_id: str,
    limit: int = Query(default=50, le=100),
    agent: Agent = Depends(get_current_agent),
    db: AsyncSession = Depends(get_db),
):
    """Get version history."""
    service = DocumentService(db)

    # SECURITY: Check permission before viewing version history
    has_access = await service.check_permission(
        UUID(document_id), agent.id, PermissionLevel.VIEWER
    )
    if not has_access:
        raise HTTPException(status_code=403, detail="Access denied")

    versions = await service.get_versions(UUID(document_id), limit)

    return [
        {
            "id": str(v.id),
            "version_number": v.version_number,
            "change_summary": v.change_summary,
            "editor_id": str(v.editor_id) if v.editor_id else None,
            "created_at": v.created_at.isoformat(),
        }
        for v in versions
    ]


@router.post("/{document_id}/versions/{version_number}/restore")
async def restore_version(
    document_id: str,
    version_number: int,
    agent: Agent = Depends(get_current_agent),
    db: AsyncSession = Depends(get_db),
):
    """Restore a previous version."""
    service = DocumentService(db)

    # SECURITY: Check editor permission before restoring version
    has_access = await service.check_permission(
        UUID(document_id), agent.id, PermissionLevel.EDITOR
    )
    if not has_access:
        raise HTTPException(status_code=403, detail="Edit access denied")

    doc = await service.restore_version(
        UUID(document_id), version_number, agent.id
    )

    return {
        "id": str(doc.id),
        "version": doc.version,
    }


@router.get("/{document_id}/comments")
async def get_comments(
    document_id: str,
    include_resolved: bool = False,
    agent: Agent = Depends(get_current_agent),
    db: AsyncSession = Depends(get_db),
):
    """Get document comments."""
    service = DocumentService(db)

    # SECURITY: Check permission before viewing comments
    has_access = await service.check_permission(
        UUID(document_id), agent.id, PermissionLevel.VIEWER
    )
    if not has_access:
        raise HTTPException(status_code=403, detail="Access denied")

    comments = await service.get_comments(UUID(document_id), include_resolved)

    return [
        {
            "id": str(c.id),
            "content": c.content,
            "author_id": str(c.author_id),
            "parent_id": str(c.parent_id) if c.parent_id else None,
            "is_suggestion": c.is_suggestion,
            "is_resolved": c.is_resolved,
            "created_at": c.created_at.isoformat(),
        }
        for c in comments
    ]


@router.post("/{document_id}/comments")
async def add_comment(
    document_id: str,
    request: AddCommentRequest,
    agent: Agent = Depends(get_current_agent),
    db: AsyncSession = Depends(get_db),
):
    """Add a comment to a document."""
    service = DocumentService(db)

    # SECURITY: Check commenter permission before adding comment
    has_access = await service.check_permission(
        UUID(document_id), agent.id, PermissionLevel.COMMENTER
    )
    if not has_access:
        raise HTTPException(status_code=403, detail="Comment access denied")

    comment = await service.add_comment(
        document_id=UUID(document_id),
        author_id=agent.id,
        content=request.content,
        parent_id=UUID(request.parent_id) if request.parent_id else None,
        anchor_type=request.anchor_type,
        anchor_data=request.anchor_data,
        is_suggestion=request.is_suggestion,
        suggested_content=request.suggested_content,
    )

    return {
        "id": str(comment.id),
        "content": comment.content,
        "is_suggestion": comment.is_suggestion,
    }


@router.post("/comments/{comment_id}/resolve")
async def resolve_comment(
    comment_id: str,
    agent: Agent = Depends(get_current_agent),
    db: AsyncSession = Depends(get_db),
):
    """Resolve a comment."""
    service = DocumentService(db)
    await service.resolve_comment(UUID(comment_id), agent.id)
    return {"status": "resolved"}


@router.post("/comments/{comment_id}/accept")
async def accept_suggestion(
    comment_id: str,
    agent: Agent = Depends(get_current_agent),
    db: AsyncSession = Depends(get_db),
):
    """Accept a suggestion."""
    service = DocumentService(db)
    doc = await service.accept_suggestion(UUID(comment_id), agent.id)
    if not doc:
        raise HTTPException(status_code=400, detail="Not a suggestion or already applied")

    return {
        "document_id": str(doc.id),
        "version": doc.version,
    }


@router.post("/folders")
async def create_folder(
    request: CreateFolderRequest,
    agent: Agent = Depends(get_current_agent),
    db: AsyncSession = Depends(get_db),
):
    """Create a folder."""
    service = DocumentService(db)
    folder = await service.create_folder(
        name=request.name,
        owner_id=agent.id,
        parent_id=UUID(request.parent_id) if request.parent_id else None,
    )

    return {
        "id": str(folder.id),
        "name": folder.name,
    }
