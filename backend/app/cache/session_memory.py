from __future__ import annotations

import json

import redis.asyncio as aioredis

from app.config import get_settings


def _key(session_id: str) -> str:
    return f"session:{session_id}:turns"


async def push_turn(
    redis: aioredis.Redis,
    session_id: str,
    role: str,
    content: str,
) -> None:
    """Append one message turn and reset the TTL."""
    ttl = get_settings().session_ttl_seconds
    k = _key(session_id)
    await redis.rpush(k, json.dumps({"role": role, "content": content}))
    await redis.expire(k, ttl)


async def get_turns(
    redis: aioredis.Redis,
    session_id: str,
    limit: int = 20,
) -> list[dict[str, str]]:
    """Return up to `limit` most-recent turns in chronological order."""
    raw: list[str] = await redis.lrange(_key(session_id), -limit, -1)
    out: list[dict[str, str]] = []
    for item in raw:
        try:
            out.append(json.loads(item))
        except json.JSONDecodeError:
            continue
    return out


async def clear_session(redis: aioredis.Redis, session_id: str) -> None:
    await redis.delete(_key(session_id))
