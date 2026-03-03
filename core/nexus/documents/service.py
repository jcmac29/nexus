"""Documents service for collaborative editing."""

from __future__ import annotations

from datetime import datetime
from uuid import UUID
import uuid as uuid_module
import hashlib

from sqlalchemy import select, and_, or_
from sqlalchemy.ext.asyncio import AsyncSession

from nexus.documents.models import (
    Document, DocumentFolder, DocumentVersion, DocumentPermission,
    DocumentComment, DocumentActivity, DocumentType, PermissionLevel
)


class DocumentService:
    """Service for document operations."""

    def __init__(self, db: AsyncSession):
        self.db = db

    async def create_document(
        self,
        title: str,
        owner_id: UUID,
        document_type: DocumentType = DocumentType.TEXT,
        content: str | None = None,
        folder_id: UUID | None = None,
        is_public: bool = False,
        tags: list[str] | None = None,
        ai_agent_id: UUID | None = None,
    ) -> Document:
        """Create a new document."""
        doc = Document(
            title=title,
            owner_id=owner_id,
            document_type=document_type,
            content=content,
            folder_id=folder_id,
            is_public=is_public,
            tags=tags or [],
            ai_agent_id=ai_agent_id,
            word_count=len(content.split()) if content else 0,
            character_count=len(content) if content else 0,
        )

        if is_public:
            doc.public_link_id = str(uuid_module.uuid4())[:8]

        self.db.add(doc)
        await self.db.flush()

        # Create initial version
        version = DocumentVersion(
            document_id=doc.id,
            version_number=1,
            content=content,
            content_hash=hashlib.sha256(content.encode()).hexdigest() if content else None,
            editor_id=owner_id,
            editor_type="agent",
            change_summary="Initial version",
        )
        self.db.add(version)

        # Log activity
        activity = DocumentActivity(
            document_id=doc.id,
            actor_id=owner_id,
            actor_type="agent",
            action="created",
        )
        self.db.add(activity)

        await self.db.commit()
        await self.db.refresh(doc)
        return doc

    async def update_document(
        self,
        document_id: UUID,
        editor_id: UUID,
        content: str | None = None,
        title: str | None = None,
        tags: list[str] | None = None,
        change_summary: str | None = None,
    ) -> Document:
        """Update a document."""
        result = await self.db.execute(
            select(Document).where(Document.id == document_id)
        )
        doc = result.scalar_one_or_none()
        if not doc:
            raise ValueError("Document not found")

        # Check for actual content change
        content_changed = content is not None and content != doc.content

        if title is not None:
            doc.title = title
        if tags is not None:
            doc.tags = tags
        if content is not None:
            doc.content = content
            doc.word_count = len(content.split())
            doc.character_count = len(content)

        doc.last_editor_id = editor_id
        doc.updated_at = datetime.utcnow()

        # Create new version if content changed
        if content_changed:
            doc.version += 1
            version = DocumentVersion(
                document_id=doc.id,
                version_number=doc.version,
                content=content,
                content_hash=hashlib.sha256(content.encode()).hexdigest(),
                editor_id=editor_id,
                editor_type="agent",
                change_summary=change_summary,
            )
            self.db.add(version)

            # Log activity
            activity = DocumentActivity(
                document_id=doc.id,
                actor_id=editor_id,
                actor_type="agent",
                action="edited",
                details={"version": doc.version},
            )
            self.db.add(activity)

        await self.db.commit()
        await self.db.refresh(doc)
        return doc

    async def get_document(
        self,
        document_id: UUID,
        viewer_id: UUID | None = None,
    ) -> Document | None:
        """Get a document."""
        result = await self.db.execute(
            select(Document).where(Document.id == document_id)
        )
        doc = result.scalar_one_or_none()

        if doc and viewer_id:
            doc.last_viewed_at = datetime.utcnow()

            activity = DocumentActivity(
                document_id=doc.id,
                actor_id=viewer_id,
                actor_type="agent",
                action="viewed",
            )
            self.db.add(activity)
            await self.db.commit()

        return doc

    async def delete_document(self, document_id: UUID, soft: bool = True):
        """Delete a document."""
        result = await self.db.execute(
            select(Document).where(Document.id == document_id)
        )
        doc = result.scalar_one_or_none()
        if not doc:
            return

        if soft:
            doc.is_trashed = True
            doc.trashed_at = datetime.utcnow()
        else:
            await self.db.delete(doc)

        await self.db.commit()

    async def list_documents(
        self,
        owner_id: UUID,
        folder_id: UUID | None = None,
        document_type: DocumentType | None = None,
        include_shared: bool = True,
        include_trashed: bool = False,
        limit: int = 50,
    ) -> list[Document]:
        """List documents."""
        query = select(Document).where(Document.owner_id == owner_id)

        if folder_id:
            query = query.where(Document.folder_id == folder_id)
        if document_type:
            query = query.where(Document.document_type == document_type)
        if not include_trashed:
            query = query.where(Document.is_trashed == False)

        query = query.order_by(Document.updated_at.desc()).limit(limit)

        result = await self.db.execute(query)
        docs = list(result.scalars().all())

        # Include shared documents
        if include_shared:
            shared_query = (
                select(Document)
                .join(DocumentPermission)
                .where(
                    and_(
                        DocumentPermission.grantee_id == owner_id,
                        Document.is_trashed == False,
                    )
                )
                .limit(limit)
            )
            shared_result = await self.db.execute(shared_query)
            shared_docs = list(shared_result.scalars().all())
            docs.extend(shared_docs)

        return docs

    async def share_document(
        self,
        document_id: UUID,
        grantee_id: UUID | None = None,
        grantee_email: str | None = None,
        permission: PermissionLevel = PermissionLevel.VIEWER,
        invited_by_id: UUID | None = None,
        expires_at: datetime | None = None,
    ) -> DocumentPermission:
        """Share a document."""
        perm = DocumentPermission(
            document_id=document_id,
            grantee_id=grantee_id,
            grantee_email=grantee_email,
            permission=permission,
            invited_by_id=invited_by_id,
            expires_at=expires_at,
        )
        self.db.add(perm)

        # Log activity
        activity = DocumentActivity(
            document_id=document_id,
            actor_id=invited_by_id,
            actor_type="agent",
            action="shared",
            details={
                "grantee_id": str(grantee_id) if grantee_id else None,
                "grantee_email": grantee_email,
                "permission": permission.value,
            },
        )
        self.db.add(activity)

        await self.db.commit()
        await self.db.refresh(perm)
        return perm

    async def check_permission(
        self,
        document_id: UUID,
        user_id: UUID,
        required: PermissionLevel,
    ) -> bool:
        """Check if user has required permission."""
        result = await self.db.execute(
            select(Document).where(Document.id == document_id)
        )
        doc = result.scalar_one_or_none()
        if not doc:
            return False

        # Owner has all permissions
        if doc.owner_id == user_id:
            return True

        # Check explicit permission
        result = await self.db.execute(
            select(DocumentPermission).where(
                and_(
                    DocumentPermission.document_id == document_id,
                    DocumentPermission.grantee_id == user_id,
                )
            )
        )
        perm = result.scalar_one_or_none()

        if not perm:
            # Check public access
            if doc.is_public and required == PermissionLevel.VIEWER:
                return True
            return False

        # Check expiry
        if perm.expires_at and perm.expires_at < datetime.utcnow():
            return False

        # Permission hierarchy
        hierarchy = {
            PermissionLevel.OWNER: 4,
            PermissionLevel.EDITOR: 3,
            PermissionLevel.COMMENTER: 2,
            PermissionLevel.VIEWER: 1,
        }

        return hierarchy.get(perm.permission, 0) >= hierarchy.get(required, 0)

    async def add_comment(
        self,
        document_id: UUID,
        author_id: UUID,
        content: str,
        parent_id: UUID | None = None,
        anchor_type: str | None = None,
        anchor_data: dict | None = None,
        is_suggestion: bool = False,
        suggested_content: str | None = None,
    ) -> DocumentComment:
        """Add a comment to a document."""
        comment = DocumentComment(
            document_id=document_id,
            author_id=author_id,
            content=content,
            parent_id=parent_id,
            anchor_type=anchor_type,
            anchor_data=anchor_data,
            is_suggestion=is_suggestion,
            suggested_content=suggested_content,
        )
        self.db.add(comment)

        # Log activity
        activity = DocumentActivity(
            document_id=document_id,
            actor_id=author_id,
            actor_type="agent",
            action="commented" if not is_suggestion else "suggested",
        )
        self.db.add(activity)

        await self.db.commit()
        await self.db.refresh(comment)
        return comment

    async def get_comments(
        self,
        document_id: UUID,
        include_resolved: bool = False,
    ) -> list[DocumentComment]:
        """Get comments on a document."""
        query = select(DocumentComment).where(
            DocumentComment.document_id == document_id
        )
        if not include_resolved:
            query = query.where(DocumentComment.is_resolved == False)

        query = query.order_by(DocumentComment.created_at.asc())

        result = await self.db.execute(query)
        return list(result.scalars().all())

    async def resolve_comment(
        self,
        comment_id: UUID,
        resolved_by_id: UUID,
    ):
        """Resolve a comment thread."""
        result = await self.db.execute(
            select(DocumentComment).where(DocumentComment.id == comment_id)
        )
        comment = result.scalar_one_or_none()
        if comment:
            comment.is_resolved = True
            comment.resolved_by_id = resolved_by_id
            comment.resolved_at = datetime.utcnow()
            await self.db.commit()

    async def accept_suggestion(
        self,
        comment_id: UUID,
        accepted_by_id: UUID,
    ) -> Document | None:
        """Accept a suggestion and apply it."""
        result = await self.db.execute(
            select(DocumentComment).where(
                and_(
                    DocumentComment.id == comment_id,
                    DocumentComment.is_suggestion == True,
                )
            )
        )
        comment = result.scalar_one_or_none()
        if not comment or not comment.suggested_content:
            return None

        # Apply the suggestion
        doc = await self.update_document(
            document_id=comment.document_id,
            editor_id=accepted_by_id,
            content=comment.suggested_content,
            change_summary=f"Applied suggestion from comment",
        )

        comment.suggestion_accepted = True
        comment.is_resolved = True
        comment.resolved_by_id = accepted_by_id
        comment.resolved_at = datetime.utcnow()

        await self.db.commit()
        return doc

    async def get_versions(
        self,
        document_id: UUID,
        limit: int = 50,
    ) -> list[DocumentVersion]:
        """Get version history."""
        result = await self.db.execute(
            select(DocumentVersion)
            .where(DocumentVersion.document_id == document_id)
            .order_by(DocumentVersion.version_number.desc())
            .limit(limit)
        )
        return list(result.scalars().all())

    async def restore_version(
        self,
        document_id: UUID,
        version_number: int,
        restored_by_id: UUID,
    ) -> Document:
        """Restore a document to a previous version."""
        result = await self.db.execute(
            select(DocumentVersion).where(
                and_(
                    DocumentVersion.document_id == document_id,
                    DocumentVersion.version_number == version_number,
                )
            )
        )
        version = result.scalar_one_or_none()
        if not version:
            raise ValueError("Version not found")

        return await self.update_document(
            document_id=document_id,
            editor_id=restored_by_id,
            content=version.content,
            change_summary=f"Restored from version {version_number}",
        )

    async def create_folder(
        self,
        name: str,
        owner_id: UUID,
        parent_id: UUID | None = None,
    ) -> DocumentFolder:
        """Create a folder."""
        folder = DocumentFolder(
            name=name,
            owner_id=owner_id,
            parent_id=parent_id,
        )
        self.db.add(folder)
        await self.db.commit()
        await self.db.refresh(folder)
        return folder

    async def search_documents(
        self,
        owner_id: UUID,
        query: str,
        limit: int = 20,
    ) -> list[Document]:
        """Search documents by title and content."""
        result = await self.db.execute(
            select(Document)
            .where(
                and_(
                    Document.owner_id == owner_id,
                    Document.is_trashed == False,
                    or_(
                        Document.title.ilike(f"%{query}%"),
                        Document.content.ilike(f"%{query}%"),
                    ),
                )
            )
            .order_by(Document.updated_at.desc())
            .limit(limit)
        )
        return list(result.scalars().all())
