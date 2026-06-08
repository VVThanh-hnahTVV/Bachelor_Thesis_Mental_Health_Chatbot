"""Rolling conversation summary — MongoDB source of truth + Redis cache."""

from __future__ import annotations

import asyncio
import logging
from typing import Any

from bson import ObjectId
from langchain_core.messages import HumanMessage, SystemMessage

from app.config import ProviderName, get_settings
from app.db.repository import get_conversation_summary, update_conversation_summary
from app.llm.factory import default_provider, get_chat_model, invoke_with_fallback

logger = logging.getLogger(__name__)

_SYSTEM = """\
You maintain a concise rolling summary of a chat session.

Given:
- Previous summary (may be empty on the first turn)
- The latest user message and assistant reply

Produce an UPDATED summary that:
- Merges new facts, topics, symptoms, and user goals from this turn
- Keeps important context from the previous summary
- Drops redundant or superseded details
- Uses the same language as the user when possible
- Stays under 12 sentences

Output ONLY the updated summary text. No headings, labels, or markdown fences.
"""


async def _generate_incremental_summary(
    *,
    previous_summary: str,
    user_message: str,
    assistant_reply: str,
    provider: ProviderName,
) -> str:
    prev = (previous_summary or "").strip() or "(none yet)"
    human = (
        f"Previous summary:\n{prev}\n\n"
        f"Latest user message:\n{user_message.strip()}\n\n"
        f"Latest assistant reply:\n{assistant_reply.strip()}\n\n"
        "Updated summary:"
    )
    max_tokens = get_settings().conversation_summary_max_tokens
    llm = get_chat_model(provider)
    msg = await invoke_with_fallback(
        llm,
        [SystemMessage(content=_SYSTEM), HumanMessage(content=human)],
        primary=provider,
        label="conversation_summary.update",
        max_tokens=max_tokens,
    )
    text = msg.content if isinstance(msg.content, str) else str(msg.content)
    return text.strip()


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
