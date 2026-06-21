"""Helpers to load conversation summary and format recent user turns."""

from __future__ import annotations

from typing import Any

from bson import ObjectId
from langchain_core.messages import BaseMessage, HumanMessage


def build_agent_memory_context(
    *,
    conversation_summary: str = "",
    user_long_term_memory: str = "",
    messages: list[BaseMessage] | list[Any],
    current_input: str = "",
    prior_user_questions: list[str] | None = None,
    recent_questions_limit: int = 5,
) -> str:
    """Memory block for Helios agents — session summary, recent turns, and user LTM."""
    summary = (conversation_summary or "").strip() or "(none yet)"
    ltm = (user_long_term_memory or "").strip() or "(none yet)"
    recent_questions = resolve_recent_user_questions(
        messages,
        prior_user_questions=prior_user_questions,
        limit=recent_questions_limit,
        exclude_current=current_input,
    )
    return (
        f"CONVERSATION SUMMARY (session, short-term):\n"
        f"{summary}\n\n"
        f"RECENT USER QUESTIONS (session, short-term — up to {recent_questions_limit} "
        f"prior turns, excluding current input — 1 = most recent, higher = older):\n"
        f"{recent_questions}\n\n"
        f"USER LONG-TERM MEMORY (cross-session, logged-in only):\n"
        f"{ltm}"
    )


def format_recent_user_questions(
    messages: list[BaseMessage] | list[Any],
    *,
    limit: int = 5,
    exclude_current: str | None = None,
) -> str:
    """Return up to `limit` prior user questions, newest first (1 = most recent)."""
    picked = _pick_recent_user_questions_from_messages(
        messages,
        limit=limit,
        exclude_current=exclude_current,
    )
    return _format_question_list(picked)


def resolve_recent_user_questions(
    messages: list[BaseMessage] | list[Any],
    *,
    prior_user_questions: list[str] | None = None,
    limit: int = 5,
    exclude_current: str | None = None,
) -> str:
    """Prefer LangGraph messages; fall back to Mongo-loaded prior questions."""
    from_messages = _pick_recent_user_questions_from_messages(
        messages,
        limit=limit,
        exclude_current=exclude_current,
    )
    if len(from_messages) >= limit or not prior_user_questions:
        return _format_question_list(from_messages)

    exclude = (exclude_current or "").strip()
    merged: list[str] = []
    seen: set[str] = set()
    for text in from_messages:
        if text not in seen:
            merged.append(text)
            seen.add(text)
    for text in prior_user_questions:
        if len(merged) >= limit:
            break
        if not text or text == exclude or text in seen:
            continue
        merged.append(text)
        seen.add(text)
    return _format_question_list(merged)


def _pick_recent_user_questions_from_messages(
    messages: list[BaseMessage] | list[Any],
    *,
    limit: int,
    exclude_current: str | None,
) -> list[str]:
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
    return picked


def _format_question_list(picked: list[str]) -> str:
    if not picked:
        return "(none)"
    return "\n".join(f"{i}. {line}" for i, line in enumerate(picked, start=1))


async def load_recent_user_questions_from_db(
    db: Any,
    conversation_id: ObjectId,
    *,
    limit: int = 5,
    exclude_current: str | None = None,
) -> list[str]:
    """Load recent user messages from MongoDB (newest first, excluding current)."""
    from app.db.repository import list_messages_for_user

    docs = await list_messages_for_user(
        db,
        conversation_id=conversation_id,
        limit=max(limit * 4, 20),
    )
    exclude = (exclude_current or "").strip()
    picked: list[str] = []
    for doc in reversed(docs):
        if str(doc.get("role") or "") != "user":
            continue
        text = str(doc.get("content") or "").strip()
        if not text or text == exclude:
            continue
        picked.append(text)
        if len(picked) >= limit:
            break
    return picked


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
