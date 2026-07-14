"""Helpers to load conversation summary and format recent conversation turns."""

from __future__ import annotations

import re
from typing import Any

from bson import ObjectId
from langchain_core.messages import AIMessage, BaseMessage, HumanMessage

# The recent-turns block is injected into several LLM calls per turn (input
# guardrail, routing, executing agent), so each part carries a hard budget:
# questions stay near-verbatim, assistant replies become short excerpts with
# a larger allowance for the most recent one.
RECENT_TURNS_LIMIT = 5
_QUESTION_MAX_CHARS = 400
_LAST_ANSWER_MAX_CHARS = 500
_OLDER_ANSWER_MAX_CHARS = 300
# Executing agents get the previous reply near-verbatim: offers and clarifying
# questions live in its tail ("tôi có thể lập một kế hoạch 7 ngày..."), and the
# user's next message is often an answer to them. Guardrail and routing keep
# the short excerpt — they only need the topic, not the wording.
_AGENT_LAST_ANSWER_MAX_CHARS = 2000


def build_agent_memory_context(
    *,
    conversation_summary: str = "",
    user_long_term_memory: str = "",
    messages: list[BaseMessage] | list[Any],
    current_input: str = "",
    prior_turns: list[dict[str, str]] | None = None,
    recent_turns_limit: int = RECENT_TURNS_LIMIT,
) -> str:
    """Memory block for Helios agents — session summary, recent turns, and user LTM."""
    summary = (conversation_summary or "").strip() or "(none yet)"
    ltm = (user_long_term_memory or "").strip() or "(none yet)"
    recent_turns = format_recent_turns(
        resolve_recent_turns(
            messages,
            prior_turns=prior_turns,
            limit=recent_turns_limit,
            exclude_current=current_input,
        ),
        last_answer_max_chars=_AGENT_LAST_ANSWER_MAX_CHARS,
    )
    return (
        f"CONVERSATION SUMMARY (session, short-term):\n"
        f"{summary}\n\n"
        f"RECENT TURNS (session, short-term — up to {recent_turns_limit} prior "
        f"question/answer pairs, excluding current input — 1 = most recent, "
        f"higher = older; turn 1's Helios reply is near-verbatim and may contain "
        f"a question or offer you made that the current message answers; older "
        f"replies are truncated excerpts):\n"
        f"{recent_turns}\n\n"
        f"RELEVANT PAST SESSIONS (cross-session episodic memory, retrieved by "
        f"relevance to the current question; logged-in users only):\n"
        f"{ltm}"
    )


def resolve_recent_turns(
    messages: list[BaseMessage] | list[Any],
    *,
    prior_turns: list[dict[str, str]] | None = None,
    limit: int = RECENT_TURNS_LIMIT,
    exclude_current: str | None = None,
) -> list[dict[str, str]]:
    """Q&A pairs, newest first — LangGraph messages topped up from Mongo turns.

    Each pair is ``{"user": ..., "assistant": ...}``; assistant may be empty
    (e.g. the turn was blocked before an answer was produced).
    """
    from_messages = _finalize_pairs(
        _pairs_from_messages(messages),
        limit=limit,
        exclude_current=exclude_current,
    )
    if len(from_messages) >= limit or not prior_turns:
        return from_messages

    exclude = (exclude_current or "").strip()
    merged = list(from_messages)
    seen = {pair["user"] for pair in merged}
    for item in prior_turns:
        if len(merged) >= limit:
            break
        question = str((item or {}).get("user") or "").strip()
        answer = str((item or {}).get("assistant") or "").strip()
        if not question or question in seen:
            continue
        if question == exclude and not answer:
            continue
        merged.append({"user": question, "assistant": answer})
        seen.add(question)
    return merged


def format_recent_turns(
    turns: list[dict[str, str]],
    *,
    last_answer_max_chars: int = _LAST_ANSWER_MAX_CHARS,
) -> str:
    """Numbered block (1 = most recent) with per-part truncation budgets."""
    if not turns:
        return "(none)"
    lines: list[str] = []
    for i, turn in enumerate(turns, start=1):
        question = _truncate_excerpt(
            str(turn.get("user") or ""), max_chars=_QUESTION_MAX_CHARS
        )
        answer = str(turn.get("assistant") or "").strip()
        budget = last_answer_max_chars if i == 1 else _OLDER_ANSWER_MAX_CHARS
        answer_text = _truncate_excerpt(answer, max_chars=budget) if answer else "(no reply)"
        lines.append(f"{i}. User: {question}\n   Helios: {answer_text}")
    return "\n".join(lines)


def _pairs_from_messages(
    messages: list[BaseMessage] | list[Any],
) -> list[dict[str, str]]:
    """Chronological Q&A pairs; each AI message answers the latest open question."""
    pairs: list[dict[str, str]] = []
    for msg in messages:
        if isinstance(msg, HumanMessage):
            text = str(msg.content or "").strip()
            pairs.append({"user": text, "assistant": ""})
        elif isinstance(msg, AIMessage):
            text = str(msg.content or "").strip()
            if text and pairs and not pairs[-1]["assistant"]:
                pairs[-1]["assistant"] = text
    return pairs


def _finalize_pairs(
    pairs_chronological: list[dict[str, str]],
    *,
    limit: int,
    exclude_current: str | None,
) -> list[dict[str, str]]:
    """Newest first, dropping empty questions and the in-flight current turn."""
    exclude = (exclude_current or "").strip()
    picked: list[dict[str, str]] = []
    for pair in reversed(pairs_chronological):
        if not pair["user"]:
            continue
        if pair["user"] == exclude and not pair["assistant"]:
            continue
        picked.append(pair)
        if len(picked) >= limit:
            break
    return picked


def _truncate_excerpt(text: str, *, max_chars: int = 500) -> str:
    collapsed = re.sub(r"\s+", " ", text.strip())
    if len(collapsed) > max_chars:
        return collapsed[: max_chars - 3].rstrip() + "..."
    return collapsed


def build_routing_conversation_section(
    *,
    conversation_summary: str = "",
    messages: list[BaseMessage] | list[Any],
    current_input: str = "",
    prior_turns: list[dict[str, str]] | None = None,
    recent_turns_limit: int = RECENT_TURNS_LIMIT,
    user_long_term_memory: str = "",
) -> str:
    """Conversation block embedded in the routing system prompt (per request)."""
    summary = (conversation_summary or "").strip() or "(none yet)"
    ltm = (user_long_term_memory or "").strip() or "(none)"
    recent_turns = format_recent_turns(
        resolve_recent_turns(
            messages,
            prior_turns=prior_turns,
            limit=recent_turns_limit,
            exclude_current=current_input,
        )
    )
    return (
        f"SESSION SUMMARY:\n{summary}\n\n"
        f"RECENT TURNS (question/answer pairs, newest first — 1 = immediately "
        f"before the current message; Helios replies are truncated excerpts):\n"
        f"{recent_turns}\n\n"
        f"RELEVANT PAST SESSIONS (episodic memory from the user's previous sessions, "
        f"most relevant first — when the session context above is empty, short/vague "
        f"messages usually continue the most recent past session's topic):\n{ltm}"
    )


async def load_recent_turns_from_db(
    db: Any,
    conversation_id: ObjectId,
    *,
    limit: int = RECENT_TURNS_LIMIT,
    exclude_current: str | None = None,
) -> list[dict[str, str]]:
    """Load recent Q&A pairs from MongoDB (newest first, excluding current)."""
    from app.db.repository import list_messages_for_user

    docs = await list_messages_for_user(
        db,
        conversation_id=conversation_id,
        limit=max(limit * 4, 20),
    )
    pairs: list[dict[str, str]] = []
    for doc in docs:
        role = str(doc.get("role") or "")
        text = str(doc.get("content") or "").strip()
        if role == "user":
            pairs.append({"user": text, "assistant": ""})
        elif role == "assistant" and text and pairs and not pairs[-1]["assistant"]:
            pairs[-1]["assistant"] = text
    return _finalize_pairs(pairs, limit=limit, exclude_current=exclude_current)


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
