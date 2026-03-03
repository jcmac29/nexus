"""Documents module - Collaborative document editing for AI and human agents."""

from nexus.documents.models import (
    Document, DocumentFolder, DocumentVersion,
    DocumentPermission, DocumentComment, DocumentActivity
)
from nexus.documents.service import DocumentService
from nexus.documents.routes import router

__all__ = [
    "Document", "DocumentFolder", "DocumentVersion",
    "DocumentPermission", "DocumentComment", "DocumentActivity",
    "DocumentService", "router"
]
