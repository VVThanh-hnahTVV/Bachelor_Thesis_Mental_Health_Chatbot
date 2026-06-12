"""Rolling conversation summary — MongoDB source of truth + Redis cache."""

from __future__ import annotations

import asyncio
import logging
from typing import Any

from bson import ObjectId

from app.config import ProviderName
from app.db.repository import get_conversation_summary, update_conversation_summary
from app.conversation.summary_markdown import generate_ai_rolling_summary
from app.llm.factory import default_provider

logger = logging.getLogger(__name__)

_SYSTEM = """\
You maintain a concise rolling summary of a chat session.

Given:
- Previous summary (may be empty on the first turn)
- The latest user message and assistant reply

Produce an UPDATED summary in Markdown with these sections:

## Chủ đề chính
## Triệu chứng / mối quan tâm
## Bối cảnh quan trọng
## Hành động / gợi ý đã đưa

Rules:
- Merge new facts; drop redundant details
- Same language as the user when possible
- Output Markdown only (no outer code fences)
- Stay under ~12 sentences total
"""


async def _generate_incremental_summary(
    *,
    previous_summary: str,
    user_message: str,
    assistant_reply: str,
    provider: ProviderName,
) -> str:
    return await generate_ai_rolling_summary(
        previous_summary=previous_summary,
        user_message=user_message,
        assistant_reply=assistant_reply,
        provider=provider,
    )


async def run_conversation_summary_update(
    db: Any,
    redis: Any,
    *,
    session_id: str,
    conversation_id: ObjectId,
    user_message: str,
    assistant_reply: str,
    provider: ProviderName | None = None,
) -> str:
    """Merge one turn into the conversation summary; persist to Mongo and Redis."""
    from app.cache.session_memory import (
        get_conversation_summary_cache,
        set_conversation_summary_cache,
    )

    user_message = user_message.strip()
    assistant_reply = assistant_reply.strip()
    if not user_message and not assistant_reply:
        return ""

    previous = ""
    if redis is not None:
        cached = await get_conversation_summary_cache(redis, session_id)
        if isinstance(cached, str) and cached.strip():
            previous = cached.strip()
    if not previous:
        previous = await get_conversation_summary(db, session_id)

    prov = provider or default_provider()
    new_summary = await _generate_incremental_summary(
        previous_summary=previous,
        user_message=user_message,
        assistant_reply=assistant_reply,
        provider=prov,
    )
    if not new_summary:
        return previous

    await update_conversation_summary(db, conversation_id, new_summary)
    if redis is not None:
        await set_conversation_summary_cache(redis, session_id, new_summary)
    return new_summary


def schedule_conversation_summary_update(
    db: Any,
    redis: Any,
    *,
    session_id: str,
    conversation_id: ObjectId,
    user_message: str,
    assistant_reply: str,
    provider: ProviderName | None = None,
) -> None:
    """Fire-and-forget summary update after the HTTP response is sent."""

    async def _run() -> None:
        try:
            await run_conversation_summary_update(
                db,
                redis,
                session_id=session_id,
                conversation_id=conversation_id,
                user_message=user_message,
                assistant_reply=assistant_reply,
                provider=provider,
            )
        except Exception as exc:  # noqa: BLE001
            logger.warning("conversation summary update failed (non-critical): %s", exc)

    asyncio.create_task(_run())
