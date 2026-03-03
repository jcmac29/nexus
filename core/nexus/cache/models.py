"""Cache models and types."""

from __future__ import annotations

import enum
from dataclasses import dataclass
from datetime import datetime
from typing import Any


class CacheBackend(str, enum.Enum):
    """Supported cache backends."""
    REDIS = "redis"
    MEMORY = "memory"
    MEMCACHED = "memcached"


@dataclass
class CacheEntry:
    """A cache entry."""
    key: str
    value: Any
    ttl: int | None = None
    created_at: datetime | None = None
    expires_at: datetime | None = None
    tags: list[str] | None = None


@dataclass
class CacheStats:
    """Cache statistics."""
    hits: int = 0
    misses: int = 0
    keys: int = 0
    memory_used: int = 0
    hit_rate: float = 0.0
