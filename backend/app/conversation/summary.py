"""Rolling conversation summary — consolidated in batches, MongoDB + Redis cache.

The summary is NOT refreshed on every turn. A watermark on the conversation
document (`summary_covered_turns` = number of user turns already folded in)
tracks coverage; consolidation runs when more than
`summary_consolidate_after_turns` turns are pending, or earlier when the
pending transcript exceeds `summary_consolidate_after_tokens` (hybrid
trigger). Agents always receive the last 5 recent Q&A pairs separately, so
the summary may lag safely.
"""

from __future__ import annotations

import asyncio
import logging
from typing import Any

from bson import ObjectId

from app.config import ProviderName, get_settings
from app.conversation.summary_markdown import generate_ai_rolling_summary_batch
from app.db.repository import (
    CONVERSATIONS,
    count_user_messages,
    list_messages_for_last_user_turns,
    update_conversation_summary_guarded,
)
from app.llm.factory import default_provider

logger = logging.getLogger(__name__)


async def maybe_consolidate_summary(
    db: Any,
    redis: Any,
    *,
    session_id: str,
    conversation_id: ObjectId,
    provider: ProviderName | None = None,
    force: bool = False,
) -> str:
    """Fold pending turns into the summary when enough have accumulated.

    Returns the freshest known summary (updated or previous). With
    ``force=True`` any pending turn triggers consolidation — used when a
    session is finalized into episodic memory or handed to a counselor.
    """
    from app.cache.session_memory import set_conversation_summary_cache

    total = await count_user_messages(db, conversation_id)
    conv = await db[CONVERSATIONS].find_one(
        {"_id": conversation_id},
        {"summary": 1, "summary_covered_turns": 1},
    )
    if not conv:
        return ""
    previous = str(conv.get("summary") or "").strip()
    covered = min(max(int(conv.get("summary_covered_turns") or 0), 0), total)
    pending = total - covered

    if pending <= 0:
        return previous

    turns = await list_messages_for_last_user_turns(
        db,
        conversation_id=conversation_id,
        user_turns=pending,
    )
    if not turns:
        return previous

    settings = get_settings()
    if not force and pending <= settings.summary_consolidate_after_turns:
        # Hybrid trigger: the turn count alone is a poor proxy for size, so
        # consolidate early when the pending transcript is already large
        # (very long user messages), estimated at ~4 chars/token.
        est_tokens = sum(len(str(m.get("content") or "")) for m in turns) // 4
        if est_tokens <= settings.summary_consolidate_after_tokens:
            return previous

    prov = provider or default_provider()
    new_summary = await generate_ai_rolling_summary_batch(
        previous_summary=previous,
        transcript_messages=turns,
        provider=prov,
    )
    if not new_summary:
        return previous

    wrote = await update_conversation_summary_guarded(
        db,
        conversation_id,
        new_summary,
        expected_covered_turns=covered,
        covered_turns=total,
    )
    if not wrote:
        # A concurrent consolidation won the race; its result is authoritative.
        logger.info("summary consolidation skipped (watermark moved): %s", session_id)
        return previous
    if redis is not None:
        await set_conversation_summary_cache(redis, session_id, new_summary)
    logger.info(
        "summary consolidated: session=%s turns=%d->%d", session_id, covered, total
    )
    return new_summary


def schedule_summary_consolidation(
    db: Any,
    redis: Any,
    *,
    session_id: str,
    conversation_id: ObjectId,
    provider: ProviderName | None = None,
    force: bool = False,
) -> None:
    """Fire-and-forget consolidation check after the HTTP response is sent."""

    async def _run() -> None:
        try:
            await maybe_consolidate_summary(
                db,
                redis,
                session_id=session_id,
                conversation_id=conversation_id,
                provider=provider,
                force=force,
            )
        except Exception as exc:  # noqa: BLE001
            logger.warning("summary consolidation failed (non-critical): %s", exc)

    asyncio.create_task(_run())
