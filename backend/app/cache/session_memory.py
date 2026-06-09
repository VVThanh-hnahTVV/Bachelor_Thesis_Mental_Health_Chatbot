from __future__ import annotations

import json

import redis.asyncio as aioredis

from app.config import get_settings


def _key(session_id: str) -> str:
    return f"session:{session_id}:turns"


def _personalization_key(session_id: str) -> str:
    return f"session:{session_id}:personalization"


def _conversation_summary_key(session_id: str) -> str:
    return f"session:{session_id}:conversation_summary"


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
    await redis.delete(_personalization_key(session_id))
    await redis.delete(_conversation_summary_key(session_id))


async def purge_chat_session_cache(redis: aioredis.Redis | None, session_id: str) -> None:
    """Clear Redis keys tied to a therapy chat session."""
    if redis is None:
        return
    await clear_session(redis, session_id)
    await redis.delete(f"wellness:{session_id}")


async def set_personalization_context(
    redis: aioredis.Redis,
    session_id: str,
    context: dict[str, object],
) -> None:
    ttl = get_settings().session_ttl_seconds
    k = _personalization_key(session_id)
    await redis.set(k, json.dumps(context))
    await redis.expire(k, ttl)


async def get_personalization_context(
    redis: aioredis.Redis,
    session_id: str,
) -> dict[str, object] | None:
    raw = await redis.get(_personalization_key(session_id))
    if not raw:
        return None
    try:
        parsed = json.loads(raw)
    except json.JSONDecodeError:
        return None
    if not isinstance(parsed, dict):
        return None
    return parsed


async def set_conversation_summary_cache(
    redis: aioredis.Redis,
    session_id: str,
    summary: str,
) -> None:
    ttl = get_settings().session_ttl_seconds
    k = _conversation_summary_key(session_id)
    await redis.set(k, summary)
    await redis.expire(k, ttl)


async def get_conversation_summary_cache(
    redis: aioredis.Redis,
    session_id: str,
) -> str | None:
    raw = await redis.get(_conversation_summary_key(session_id))
    if raw is None:
        return None
    if isinstance(raw, bytes):
        raw = raw.decode("utf-8", errors="replace")
    text = str(raw).strip()
    return text or None
