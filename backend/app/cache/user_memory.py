from __future__ import annotations

import redis.asyncio as aioredis

from app.config import get_settings


def _key(user_id: str) -> str:
    return f"user:{user_id}:long_term_memory"


async def get_user_long_term_memory_cache(
    redis: aioredis.Redis,
    user_id: str,
) -> str | None:
    raw = await redis.get(_key(user_id))
    if raw is None:
        return None
    if isinstance(raw, bytes):
        raw = raw.decode("utf-8", errors="replace")
    text = str(raw).strip()
    return text or None


async def set_user_long_term_memory_cache(
    redis: aioredis.Redis,
    user_id: str,
    memory: str,
) -> None:
    ttl = get_settings().user_long_term_memory_cache_ttl_seconds
    k = _key(user_id)
    await redis.set(k, memory)
    await redis.expire(k, ttl)


async def delete_user_long_term_memory_cache(
    redis: aioredis.Redis,
    user_id: str,
) -> None:
    await redis.delete(_key(user_id))
