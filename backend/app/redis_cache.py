import json
import os
from typing import Any, Optional

try:
    from redis.asyncio import Redis
except ImportError:  # Redis is optional for local API-only development.
    Redis = Any

_redis: Optional[Redis] = None


def get_redis() -> Redis:
    global _redis
    if Redis is Any:
        raise RuntimeError("redis package is not installed")
    if _redis is None:
        _redis = Redis.from_url(
            os.getenv("REDIS_URL", "redis://127.0.0.1:6379/0"),
            decode_responses=True,
        )
    return _redis


async def cache_get(key: str) -> Any:
    try:
        value = await get_redis().get(key)
        return json.loads(value) if value else None
    except Exception:
        return None


async def cache_set(key: str, value: Any, ttl: int = 300) -> None:
    try:
        await get_redis().set(key, json.dumps(value, default=str), ex=ttl)
    except Exception:
        return None


async def cache_delete(key: str) -> None:
    try:
        await get_redis().delete(key)
    except Exception:
        return None
