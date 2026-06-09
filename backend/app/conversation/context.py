"""Helpers to load conversation summary and format recent user turns."""

from __future__ import annotations

from typing import Any

from langchain_core.messages import BaseMessage, HumanMessage


def build_agent_memory_context(
    *,
    conversation_summary: str = "",
    messages: list[BaseMessage] | list[Any],
    current_input: str = "",
    recent_questions_limit: int = 5,
) -> str:
    """Memory block for Helios agents — same shape as guardrails input check."""
    summary = (conversation_summary or "").strip() or "(none yet)"
    recent_questions = format_recent_user_questions(
        messages,
        limit=recent_questions_limit,
        exclude_current=current_input,
    )
    return (
        f"CONVERSATION SUMMARY (rolling, may be empty on first turn):\n"
        f"{summary}\n\n"
        f"RECENT USER QUESTIONS (up to {recent_questions_limit} prior turns, "
        f"excluding current input — 1 = most recent, higher = older):\n"
        f"{recent_questions}"
    )


def format_recent_user_questions(
    messages: list[BaseMessage] | list[Any],
    *,
    limit: int = 5,
    exclude_current: str | None = None,
) -> str:
    """Return up to `limit` prior user questions, newest first (1 = most recent)."""
    exclude = (exclude_current or "").strip()
    picked: list[str] = []
    for msg in reversed(messages):
        if not isinstance(msg, HumanMessage):
            continue
        text = str(msg.content or "").strip()
        if not text or text == exclude:
            continue
        picked.append(text)
        if len(picked) >= limit:
            break
    if not picked:
        return "(none)"
    return "\n".join(f"{i}. {line}" for i, line in enumerate(picked, start=1))


async def load_conversation_summary(
    db: Any,
    redis: Any,
    session_id: str,
) -> str:
    """Redis cache first, then MongoDB `conversations.summary`."""
    from app.cache.session_memory import get_conversation_summary_cache
    from app.db.repository import get_conversation_summary as get_summary_from_db

    if redis is not None:
        cached = await get_conversation_summary_cache(redis, session_id)
        if isinstance(cached, str) and cached.strip():
            return cached.strip()
    return await get_summary_from_db(db, session_id)
