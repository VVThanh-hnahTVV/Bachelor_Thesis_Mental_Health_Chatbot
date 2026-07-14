"""Escalate conversations to awaiting human support."""

from __future__ import annotations

import json
import logging
from datetime import UTC, datetime
from typing import Any, Literal

from bson import ObjectId

from app.db.repository import update_conversation_support_mode

logger = logging.getLogger(__name__)

HANDOFF_REDIS_CHANNEL_PREFIX = "ws:session:"


def handoff_redis_channel(session_id: str) -> str:
    return f"{HANDOFF_REDIS_CHANNEL_PREFIX}{session_id}"


async def publish_ws_event(redis: Any, session_id: str, event: dict[str, Any]) -> None:
    if redis is None:
        return
    try:
        payload = json.dumps(event, ensure_ascii=False, default=str)
        await redis.publish(handoff_redis_channel(session_id), payload)
    except Exception as exc:  # noqa: BLE001
        logger.warning("publish_ws_event failed: %s", exc)


async def escalate_to_awaiting_support(
    db: Any,
    redis: Any,
    *,
    conversation_id: ObjectId,
    session_id: str,
    source: Literal["guard", "button"] = "guard",
) -> None:
    from app.conversation.summary import schedule_summary_consolidation

    now = datetime.now(UTC)
    await update_conversation_support_mode(
        db,
        conversation_id,
        "awaiting_support",
        extra={"handoff_requested_at": now},
    )
    # Flush the rolling summary now so the handoff brief is fresh when a
    # counselor joins, without adding latency to either request.
    schedule_summary_consolidation(
        db,
        redis,
        session_id=session_id,
        conversation_id=conversation_id,
        force=True,
    )
    await publish_ws_event(
        redis,
        session_id,
        {
            "type": "handoff_pending",
            "session_id": session_id,
            "source": source,
        },
    )
