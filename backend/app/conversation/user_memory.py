"""Cross-session user memory.

Long-term memory is episodic (see `app.conversation.episodic_memory`): one
record per finished session, retrieved by relevance at chat time. The old
per-turn merged profile (`users.long_term_memory`) is no longer written;
`load_user_long_term_memory` remains only to read legacy data.
"""

from __future__ import annotations

import asyncio
import logging
from typing import Any

from bson import ObjectId

from app.auth.repository import get_user_long_term_memory
from app.config import ProviderName

logger = logging.getLogger(__name__)


async def load_user_long_term_memory(
    db: Any,
    redis: Any,
    user_id: ObjectId,
) -> str:
    """Legacy merged-profile read (Redis cache first, then MongoDB)."""
    from app.cache.user_memory import get_user_long_term_memory_cache

    uid = str(user_id)
    if redis is not None:
        cached = await get_user_long_term_memory_cache(redis, uid)
        if isinstance(cached, str) and cached.strip():
            return cached.strip()
    return await get_user_long_term_memory(db, user_id)


def schedule_post_turn_memory_updates(
    db: Any,
    redis: Any,
    *,
    session_id: str,
    conversation_id: ObjectId,
    provider: ProviderName | None = None,
) -> None:
    """Post-turn background work: consolidate the rolling summary when due.

    Long-term memory is NOT touched here anymore — sessions are folded into
    episodic memory at session boundaries (new-session start, handoff leave).
    """

    async def _run() -> None:
        from app.conversation.summary import maybe_consolidate_summary

        try:
            await maybe_consolidate_summary(
                db,
                redis,
                session_id=session_id,
                conversation_id=conversation_id,
                provider=provider,
            )
        except Exception as exc:  # noqa: BLE001
            logger.warning("post-turn summary consolidation failed (non-critical): %s", exc)

    asyncio.create_task(_run())
