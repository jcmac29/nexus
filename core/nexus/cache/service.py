"""Redis cache service for Nexus."""

from __future__ import annotations

import json
from datetime import datetime, timedelta, timezone
from typing import Any, TypeVar, Callable
from functools import wraps
import hashlib

T = TypeVar("T")


class SecureJSONEncoder(json.JSONEncoder):
    """JSON encoder that handles common Python types safely."""

    def default(self, obj):
        if isinstance(obj, datetime):
            return {"__datetime__": obj.isoformat()}
        if isinstance(obj, timedelta):
            return {"__timedelta__": obj.total_seconds()}
        if hasattr(obj, "__dict__"):
            # For simple objects, serialize their dict (but not arbitrary objects)
            return {"__type__": type(obj).__name__, "__data__": str(obj)}
        return super().default(obj)


def secure_json_decode(obj):
    """Decode JSON with special type handling."""
    if isinstance(obj, dict):
        if "__datetime__" in obj:
            return datetime.fromisoformat(obj["__datetime__"])
        if "__timedelta__" in obj:
            return timedelta(seconds=obj["__timedelta__"])
    return obj


def safe_serialize(value: Any) -> bytes:
    """Safely serialize a value to JSON bytes. No pickle allowed."""
    return json.dumps(value, cls=SecureJSONEncoder).encode("utf-8")


def safe_deserialize(data: bytes) -> Any:
    """Safely deserialize JSON bytes. No pickle allowed."""
    return json.loads(data.decode("utf-8"), object_hook=secure_json_decode)


class CacheService:
    """Redis-based caching service."""

    def __init__(self, redis_url: str = "redis://localhost:6379"):
        self._redis_url = redis_url
        self._redis = None
        self._local_cache: dict[str, Any] = {}
        self._stats = {"hits": 0, "misses": 0}

    async def connect(self):
        """Connect to Redis."""
        import redis.asyncio as redis
        self._redis = redis.from_url(self._redis_url, decode_responses=False)
        await self._redis.ping()

    async def disconnect(self):
        """Disconnect from Redis."""
        if self._redis:
            await self._redis.close()

    async def get(self, key: str, default: Any = None) -> Any:
        """Get a value from cache."""
        if self._redis:
            try:
                value = await self._redis.get(key)
                if value is not None:
                    self._stats["hits"] += 1
                    return safe_deserialize(value)
                self._stats["misses"] += 1
                return default
            except Exception:
                pass

        # Fallback to local cache
        if key in self._local_cache:
            entry = self._local_cache[key]
            # SECURITY: Use timezone-aware datetime to prevent token bypass
            if entry.get("expires_at") and entry["expires_at"] < datetime.now(timezone.utc):
                del self._local_cache[key]
                self._stats["misses"] += 1
                return default
            self._stats["hits"] += 1
            return entry["value"]

        self._stats["misses"] += 1
        return default

    async def set(
        self,
        key: str,
        value: Any,
        ttl: int | None = None,
        tags: list[str] | None = None,
    ):
        """Set a value in cache."""
        if self._redis:
            try:
                serialized = safe_serialize(value)
                if ttl:
                    await self._redis.setex(key, ttl, serialized)
                else:
                    await self._redis.set(key, serialized)

                # Store tags for invalidation
                if tags:
                    for tag in tags:
                        await self._redis.sadd(f"tag:{tag}", key)
                return
            except Exception:
                pass

        # Fallback to local cache
        self._local_cache[key] = {
            "value": value,
            "expires_at": datetime.now(timezone.utc) + timedelta(seconds=ttl) if ttl else None,
            "tags": tags,
        }

    async def delete(self, key: str):
        """Delete a key from cache."""
        if self._redis:
            try:
                await self._redis.delete(key)
                return
            except Exception:
                pass

        self._local_cache.pop(key, None)

    async def delete_pattern(self, pattern: str):
        """Delete all keys matching a pattern."""
        if self._redis:
            try:
                cursor = 0
                while True:
                    cursor, keys = await self._redis.scan(cursor, match=pattern, count=100)
                    if keys:
                        await self._redis.delete(*keys)
                    if cursor == 0:
                        break
                return
            except Exception:
                pass

        # Local cache pattern delete
        import fnmatch
        keys_to_delete = [k for k in self._local_cache if fnmatch.fnmatch(k, pattern)]
        for key in keys_to_delete:
            del self._local_cache[key]

    async def invalidate_tags(self, tags: list[str]):
        """Invalidate all cache entries with given tags."""
        if self._redis:
            try:
                for tag in tags:
                    keys = await self._redis.smembers(f"tag:{tag}")
                    if keys:
                        await self._redis.delete(*keys)
                    await self._redis.delete(f"tag:{tag}")
                return
            except Exception:
                pass

        # Local cache tag invalidation
        keys_to_delete = []
        for key, entry in self._local_cache.items():
            entry_tags = entry.get("tags", [])
            if entry_tags and any(t in tags for t in entry_tags):
                keys_to_delete.append(key)
        for key in keys_to_delete:
            del self._local_cache[key]

    async def get_or_set(
        self,
        key: str,
        factory: Callable[[], Any],
        ttl: int | None = None,
        tags: list[str] | None = None,
    ) -> Any:
        """Get from cache or compute and store."""
        value = await self.get(key)
        if value is not None:
            return value

        # Compute value
        if callable(factory):
            import asyncio
            if asyncio.iscoroutinefunction(factory):
                value = await factory()
            else:
                value = factory()

        await self.set(key, value, ttl=ttl, tags=tags)
        return value

    async def increment(self, key: str, amount: int = 1) -> int:
        """Increment a counter."""
        if self._redis:
            try:
                return await self._redis.incrby(key, amount)
            except Exception:
                pass

        current = self._local_cache.get(key, {"value": 0})
        new_value = current["value"] + amount
        self._local_cache[key] = {"value": new_value, "expires_at": None}
        return new_value

    async def decrement(self, key: str, amount: int = 1) -> int:
        """Decrement a counter."""
        return await self.increment(key, -amount)

    async def expire(self, key: str, ttl: int):
        """Set expiration on a key."""
        if self._redis:
            try:
                await self._redis.expire(key, ttl)
                return
            except Exception:
                pass

        if key in self._local_cache:
            self._local_cache[key]["expires_at"] = datetime.now(timezone.utc) + timedelta(seconds=ttl)

    async def ttl(self, key: str) -> int:
        """Get TTL of a key."""
        if self._redis:
            try:
                return await self._redis.ttl(key)
            except Exception:
                pass

        if key in self._local_cache:
            entry = self._local_cache[key]
            if entry.get("expires_at"):
                remaining = (entry["expires_at"] - datetime.now(timezone.utc)).total_seconds()
                return max(0, int(remaining))
        return -1

    async def exists(self, key: str) -> bool:
        """Check if key exists."""
        if self._redis:
            try:
                return await self._redis.exists(key) > 0
            except Exception:
                pass

        return key in self._local_cache

    async def flush(self):
        """Flush all cache."""
        if self._redis:
            try:
                await self._redis.flushdb()
                return
            except Exception:
                pass

        self._local_cache.clear()

    async def get_stats(self) -> dict:
        """Get cache statistics."""
        stats = {
            "hits": self._stats["hits"],
            "misses": self._stats["misses"],
            "hit_rate": self._stats["hits"] / max(1, self._stats["hits"] + self._stats["misses"]),
        }

        if self._redis:
            try:
                info = await self._redis.info("memory")
                stats["memory_used"] = info.get("used_memory", 0)
                stats["keys"] = await self._redis.dbsize()
            except Exception:
                pass
        else:
            stats["keys"] = len(self._local_cache)

        return stats

    # --- Distributed Locking ---

    async def acquire_lock(self, name: str, timeout: int = 10) -> bool:
        """Acquire a distributed lock."""
        lock_key = f"lock:{name}"
        if self._redis:
            try:
                return await self._redis.set(lock_key, "1", nx=True, ex=timeout)
            except Exception:
                pass

        # Local lock (not distributed)
        if lock_key not in self._local_cache:
            self._local_cache[lock_key] = {
                "value": "1",
                "expires_at": datetime.now(timezone.utc) + timedelta(seconds=timeout),
            }
            return True
        return False

    async def release_lock(self, name: str):
        """Release a distributed lock."""
        lock_key = f"lock:{name}"
        await self.delete(lock_key)

    # --- Rate Limiting ---

    async def rate_limit_check(
        self,
        key: str,
        limit: int,
        window_seconds: int,
    ) -> tuple[bool, int, int]:
        """
        Check rate limit using sliding window.

        Returns: (allowed, current_count, remaining)
        """
        now = datetime.now(timezone.utc).timestamp()
        window_start = now - window_seconds

        if self._redis:
            try:
                pipe = self._redis.pipeline()
                # Remove old entries
                pipe.zremrangebyscore(key, 0, window_start)
                # Add current request
                pipe.zadd(key, {str(now): now})
                # Count requests in window
                pipe.zcard(key)
                # Set expiration
                pipe.expire(key, window_seconds)

                results = await pipe.execute()
                current_count = results[2]

                allowed = current_count <= limit
                remaining = max(0, limit - current_count)
                return allowed, current_count, remaining
            except Exception:
                pass

        # Simple local rate limiting
        rate_key = f"rate:{key}"
        entry = self._local_cache.get(rate_key, {"value": [], "expires_at": None})
        timestamps = [t for t in entry["value"] if t > window_start]
        timestamps.append(now)

        self._local_cache[rate_key] = {
            "value": timestamps,
            "expires_at": datetime.now(timezone.utc) + timedelta(seconds=window_seconds),
        }

        current_count = len(timestamps)
        allowed = current_count <= limit
        remaining = max(0, limit - current_count)
        return allowed, current_count, remaining

    # --- Session Management ---

    async def set_session(self, session_id: str, data: dict, ttl: int = 3600):
        """Store session data."""
        await self.set(f"session:{session_id}", data, ttl=ttl)

    async def get_session(self, session_id: str) -> dict | None:
        """Get session data."""
        return await self.get(f"session:{session_id}")

    async def delete_session(self, session_id: str):
        """Delete session."""
        await self.delete(f"session:{session_id}")

    async def refresh_session(self, session_id: str, ttl: int = 3600):
        """Refresh session TTL."""
        await self.expire(f"session:{session_id}", ttl)


def cached(
    ttl: int = 300,
    key_prefix: str = "",
    tags: list[str] | None = None,
):
    """Decorator for caching function results."""
    def decorator(func: Callable[..., T]) -> Callable[..., T]:
        @wraps(func)
        async def wrapper(*args, **kwargs) -> T:
            # Generate cache key from function name and arguments
            key_parts = [key_prefix or func.__name__]
            key_parts.extend(str(arg) for arg in args)
            key_parts.extend(f"{k}={v}" for k, v in sorted(kwargs.items()))
            # SECURITY: Use SHA-256 instead of MD5 for cache key generation
            key = hashlib.sha256(":".join(key_parts).encode()).hexdigest()
            full_key = f"cache:{func.__name__}:{key}"

            # This requires cache service to be injected or globally available
            # For now, just execute the function
            import asyncio
            if asyncio.iscoroutinefunction(func):
                return await func(*args, **kwargs)
            return func(*args, **kwargs)

        return wrapper
    return decorator


# Global cache instance
_cache: CacheService | None = None


async def get_cache() -> CacheService:
    """Get the global cache instance."""
    global _cache
    if _cache is None:
        from nexus.config import get_settings
        settings = get_settings()
        _cache = CacheService(redis_url=getattr(settings, 'redis_url', 'redis://localhost:6379'))
        try:
            await _cache.connect()
        except Exception:
            pass  # Fall back to local cache
    return _cache
