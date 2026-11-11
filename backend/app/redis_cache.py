import json
import logging
import os
from typing import Any, Optional

try:
    from redis.asyncio import Redis
except ImportError:  # Redis is optional for local API-only development.
    Redis = Any

_redis: Optional[Redis] = None
LOG = logging.getLogger(__name__)


def get_redis() -> Redis:
    global _redis
    if Redis is Any:
        raise RuntimeError("redis package is not installed")
    if _redis is None:
        _redis = Redis.from_url(
            os.getenv("REDIS_URL", "redis://127.0.0.1:6379/0"),
            decode_responses=True,
            socket_connect_timeout=float(os.getenv("REDIS_SOCKET_TIMEOUT", "1")),
            socket_timeout=float(os.getenv("REDIS_SOCKET_TIMEOUT", "1")),
        )
    return _redis


async def close_redis() -> None:
    global _redis
    client = _redis
    _redis = None
    if client is not None:
        try:
            await client.aclose()
        except Exception as exc:
            LOG.warning("redis_close_failed error=%s", type(exc).__name__)


async def cache_get(key: str) -> Any:
    try:
        value = await get_redis().get(key)
        return json.loads(value) if value else None
    except Exception:
        return None


async def cache_set(key: str, value: Any, ttl: int = 300) -> None:
    await cache_set_checked(key, value, ttl)


async def cache_set_checked(key: str, value: Any, ttl: int = 300) -> bool:
    try:
        await get_redis().set(key, json.dumps(value, default=str), ex=ttl)
        return True
    except Exception as exc:
        LOG.warning("redis_cache_set_failed key=%s error=%s", key, type(exc).__name__)
        return False


async def refresh_hot_cache(rows: list[tuple[int, float]], ttl: int = 3600) -> bool:
    if not rows:
        return False
    try:
        client = get_redis()
        pipe = client.pipeline(transaction=True)
        pipe.delete("recom:hot:global")
        pipe.zadd("recom:hot:global", {str(movie_id): score for movie_id, score in rows})
        pipe.expire("recom:hot:global", ttl)
        await pipe.execute()
        return True
    except Exception as exc:
        LOG.warning("redis_hot_cache_refresh_failed error=%s", type(exc).__name__)
        return False


async def read_hot_cache_ids(limit: int = 100) -> list[int]:
    try:
        values = await get_redis().zrevrange("recom:hot:global", 0, limit - 1)
        return [int(value) for value in values]
    except Exception as exc:
        LOG.warning("redis_hot_cache_read_failed error=%s", type(exc).__name__)
        return []


async def cache_delete(key: str) -> None:
    try:
        await get_redis().delete(key)
    except Exception:
        return None
