"""Embedding generation for semantic search."""

import json
from functools import lru_cache

from sentence_transformers import SentenceTransformer

from nexus.config import get_settings

settings = get_settings()


@lru_cache(maxsize=1)
def get_embedding_model() -> SentenceTransformer:
    """Get the cached embedding model."""
    return SentenceTransformer(settings.embedding_model)


def generate_embedding(text: str) -> list[float]:
    """Generate an embedding vector for the given text."""
    model = get_embedding_model()
    embedding = model.encode(text, normalize_embeddings=True)
    return embedding.tolist()


def extract_text_from_value(value: dict) -> str:
    """Extract searchable text from a memory value.

    This tries to create a meaningful text representation of the value
    that can be used for semantic search.
    """
    # If it's a simple dict, convert to readable format
    if isinstance(value, dict):
        # Look for common text fields
        text_fields = ["text", "content", "message", "description", "summary", "note"]
        for field in text_fields:
            if field in value and isinstance(value[field], str):
                return value[field]

        # Fall back to JSON representation
        return json.dumps(value, indent=2, default=str)

    return str(value)
