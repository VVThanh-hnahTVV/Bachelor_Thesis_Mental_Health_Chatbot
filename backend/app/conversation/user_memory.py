"""Long-term user memory — MongoDB source of truth + Redis cache."""

from __future__ import annotations

import asyncio
import logging
from typing import Any

from bson import ObjectId

from app.auth.repository import get_user_long_term_memory, update_user_long_term_memory
from app.config import ProviderName
from app.conversation.summary_markdown import generate_user_long_term_memory_update
from app.llm.factory import default_provider

logger = logging.getLogger(__name__)


async def load_user_long_term_memory(
    db: Any,
    redis: Any,
    user_id: ObjectId,
) -> str:
    """Redis cache first, then MongoDB `users.long_term_memory`."""
    from app.cache.user_memory import get_user_long_term_memory_cache

    uid = str(user_id)
    if redis is not None:
        cached = await get_user_long_term_memory_cache(redis, uid)
        if isinstance(cached, str) and cached.strip():
            return cached.strip()
    return await get_user_long_term_memory(db, user_id)


async def run_user_long_term_memory_update(
    db: Any,
    redis: Any,
    *,
    user_id: ObjectId,
    session_summary: str,
    source: str = "ai_turn",
    provider: ProviderName | None = None,
) -> str:
    """Merge session summary into the user's long-term memory profile."""
    from app.cache.user_memory import set_user_long_term_memory_cache

    summary = (session_summary or "").strip()
    if not summary:
        return await load_user_long_term_memory(db, redis, user_id)

    previous = await load_user_long_term_memory(db, redis, user_id)
    prov = provider or default_provider()
    new_memory = await generate_user_long_term_memory_update(
        previous_memory=previous,
        session_summary=summary,
        source=source,
        provider=prov,
    )
    if not new_memory:
        return previous

    await update_user_long_term_memory(db, user_id, new_memory)
    if redis is not None:
        await set_user_long_term_memory_cache(redis, str(user_id), new_memory)
    return new_memory


def schedule_user_long_term_memory_update(
    db: Any,
    redis: Any,
    *,
    user_id: ObjectId,
    session_summary: str,
    source: str = "ai_turn",
    provider: ProviderName | None = None,
) -> None:
    """Fire-and-forget long-term memory update after chat turn or handoff leave."""

    async def _run() -> None:
        try:
            await run_user_long_term_memory_update(
                db,
                redis,
                user_id=user_id,
                session_summary=session_summary,
                source=source,
                provider=provider,
            )
        except Exception as exc:  # noqa: BLE001
            logger.warning("user long-term memory update failed (non-critical): %s", exc)

    asyncio.create_task(_run())


def schedule_post_turn_memory_updates(
    db: Any,
    redis: Any,
    *,
    session_id: str,
    conversation_id: ObjectId,
    user_id: ObjectId | None,
    user_message: str,
    assistant_reply: str,
    provider: ProviderName | None = None,
) -> None:
    """Update session summary, then long-term user memory when logged in."""

    async def _run() -> None:
        from app.conversation.summary import run_conversation_summary_update

        try:
            new_summary = await run_conversation_summary_update(
                db,
                redis,
                session_id=session_id,
                conversation_id=conversation_id,
                user_message=user_message,
                assistant_reply=assistant_reply,
                provider=provider,
            )
            if user_id is not None and new_summary.strip():
                await run_user_long_term_memory_update(
                    db,
                    redis,
                    user_id=user_id,
                    session_summary=new_summary,
                    source="ai_turn",
                    provider=provider,
                )
        except Exception as exc:  # noqa: BLE001
            logger.warning("post-turn memory update failed (non-critical): %s", exc)

    asyncio.create_task(_run())
