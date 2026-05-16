"""Node 3: memory_retrieval — gather short-term (Redis), long-term (MongoDB), and RAG chunks."""
from __future__ import annotations

import asyncio
import logging
from typing import Any

from app.rag.corpus import lexical_scores, load_chunks

logger = logging.getLogger(__name__)


async def _get_long_term(db: Any, session_id: str) -> dict[str, Any]:
    if db is None or not session_id:
        return {}
    try:
        from app.db.repository import get_mood_trend, get_user_profile
        profile_task = asyncio.create_task(get_user_profile(db, session_id))
        trend_task = asyncio.create_task(get_mood_trend(db, session_id))
        profile, trend = await asyncio.gather(profile_task, trend_task)
        ctx: dict[str, Any] = {"mood_trend": trend}
        if profile:
            ctx["recurring_stressors"] = profile.get("recurring_stressors", [])
            ctx["coping_preferences"] = profile.get("coping_preferences", [])
            ctx["preferred_tone"] = profile.get("preferred_tone", "warm")
        return ctx
    except Exception as exc:
        logger.warning("long-term memory retrieval failed: %s", exc)
        return {}


async def node_memory_retrieval(state: dict[str, Any]) -> dict[str, Any]:
    user_input: str = state.get("user_input", "")
    session_id: str = state.get("session_id", "")
    db: Any = state.get("db")

    # RAG (sync, cached)
    chunks = load_chunks()
    scored = lexical_scores(user_input, chunks, top_k=3)
    retrieved = [c["text"] for s, c in scored if s > 0]

    # Long-term MongoDB (async)
    long_term = await _get_long_term(db, session_id)

    meta = dict(state.get("metadata") or {})
    meta["retrieve_scores"] = [float(s) for s, _ in scored[:3]]
    return {
        "retrieved_chunks": retrieved,
        "long_term_context": long_term,
        "metadata": meta,
    }
