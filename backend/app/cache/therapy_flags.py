"""Per-session therapy intervention flags (Redis-backed)."""
from __future__ import annotations

import json
from typing import Any

from redis.asyncio import Redis

TTL_SEC = 7200


def _key(session_id: str) -> str:
    return f"therapy_flags:{session_id}"


async def get_therapy_flags(redis: Redis | None, session_id: str) -> dict[str, Any]:
    if redis is None:
        return {}
    raw = await redis.get(_key(session_id))
    if not raw:
        return {}
    try:
        data = json.loads(raw.decode() if isinstance(raw, bytes) else raw)
        return data if isinstance(data, dict) else {}
    except (json.JSONDecodeError, TypeError):
        return {}


async def set_therapy_flags(
    redis: Redis | None,
    session_id: str,
    flags: dict[str, Any],
) -> None:
    if redis is None:
        return
    await redis.set(_key(session_id), json.dumps(flags), ex=TTL_SEC)


async def update_therapy_flags_after_turn(
    redis: Redis | None,
    *,
    session_id: str,
    therapy_strategy: str | None,
    user_turn_count: int,
) -> dict[str, Any]:
    """Persist last strategy and record first stabilization turn."""
    flags = await get_therapy_flags(redis, session_id)
    strategy = therapy_strategy or ""
    flags["last_strategy"] = strategy
    if strategy == "stabilization" and not flags.get("stabilization_turn"):
        flags["stabilization_turn"] = user_turn_count
    await set_therapy_flags(redis, session_id, flags)
    return flags
