"""Wellness activity session FSM (Redis-backed)."""
from __future__ import annotations

import json
from datetime import UTC, datetime
from typing import Any, Literal

from redis.asyncio import Redis

WellnessStep = Literal["intro", "active", "checkin"]

TTL_SEC = 7200

_INTRO_VI = {
    "breathing_box": (
        "Mình sẽ đồng hành cùng bạn một nhịp thở đều (4-4-4-4). "
        "Khi sẵn sàng, hãy mở bài tập trong app và thử vài vòng nhé."
    ),
    "ocean_sound": (
        "Âm sóng nhẹ có thể giúp thư giãn. "
        "Mở âm nền trong app và để nó đồng hành vài phút khi bạn muốn."
    ),
}

_INTRO_EN = {
    "breathing_box": (
        "I'll guide you through steady box breathing (4-4-4-4). "
        "When ready, open the exercise in the app and try a few cycles."
    ),
    "ocean_sound": (
        "Gentle wave sounds can help you unwind. "
        "Open the ambient sound in the app for a few minutes when you're ready."
    ),
}

_CHECKIN_VI = "Bạn có cảm thấy nhẹ hơn một chút sau bài tập không?"
_CHECKIN_EN = "Do you feel a little lighter after the exercise?"


def _key(session_id: str) -> str:
    return f"wellness:{session_id}"


def _suggest_turn_key(session_id: str) -> str:
    return f"wellness_suggest_turn:{session_id}"


async def get_last_suggestion_turn(redis: Redis | None, session_id: str) -> int | None:
    if redis is None:
        return None
    raw = await redis.get(_suggest_turn_key(session_id))
    if raw is None:
        return None
    try:
        return int(raw)
    except (TypeError, ValueError):
        return None


async def mark_suggestion_turn(redis: Redis | None, session_id: str, user_turn: int) -> None:
    if redis is not None:
        await redis.set(_suggest_turn_key(session_id), str(user_turn), ex=TTL_SEC)


async def get_session(redis: Redis | None, session_id: str) -> dict[str, Any] | None:
    if redis is None:
        return None
    raw = await redis.get(_key(session_id))
    if not raw:
        return None
    try:
        return json.loads(raw)
    except json.JSONDecodeError:
        return None


async def start_session(
    redis: Redis | None,
    *,
    session_id: str,
    activity_id: str,
    lang: str = "vi",
) -> tuple[dict[str, Any], str]:
    """Start wellness session; return (state, intro_message)."""
    intro_map = _INTRO_EN if lang == "en" else _INTRO_VI
    intro = intro_map.get(
        activity_id,
        intro_map.get("breathing_box", ""),
    )
    state = {
        "activity_id": activity_id,
        "step": "intro",
        "started_at": datetime.now(UTC).isoformat(),
    }
    if redis is not None:
        await redis.set(_key(session_id), json.dumps(state), ex=TTL_SEC)
    return state, intro


async def set_active(redis: Redis | None, session_id: str) -> dict[str, Any] | None:
    state = await get_session(redis, session_id)
    if not state:
        return None
    state["step"] = "active"
    if redis is not None:
        await redis.set(_key(session_id), json.dumps(state), ex=TTL_SEC)
    return state


async def complete_session(
    redis: Redis | None,
    *,
    session_id: str,
    lang: str = "vi",
) -> tuple[dict[str, Any] | None, str]:
    """Mark checkin step; return (state, checkin_message)."""
    state = await get_session(redis, session_id)
    if not state:
        return None, ""
    state["step"] = "checkin"
    msg = _CHECKIN_EN if lang == "en" else _CHECKIN_VI
    if redis is not None:
        await redis.set(_key(session_id), json.dumps(state), ex=TTL_SEC)
    return state, msg


async def clear_session(redis: Redis | None, session_id: str) -> None:
    if redis is not None:
        await redis.delete(_key(session_id))


def is_wellness_active(state: dict[str, Any] | None) -> bool:
    if not state:
        return False
    return state.get("step") in ("intro", "active")
