"""Episodic long-term memory — one immutable record per finished session.

Replaces the ever-rewritten merged profile: when a session is finalized
(user starts a new session, or a counselor closes a handoff) its final rolling
summary is stored in MongoDB (`user_session_memories`) and embedded into a
Qdrant collection. At chat time the current query + session summary retrieve
only the top-k relevant past sessions (cosine relevance + recency boost),
which are injected into the agent memory context.
"""

from __future__ import annotations

import asyncio
import logging
import math
import uuid
from datetime import UTC, datetime
from typing import Any

from bson import ObjectId
from qdrant_client import QdrantClient
from qdrant_client.http.models import (
    Distance,
    FieldCondition,
    Filter,
    MatchValue,
    PayloadSchemaType,
    PointIdsList,
    PointStruct,
    VectorParams,
)

from app.config import get_settings
from app.medical.agents.rag_agent.vectorstore_qdrant import build_qdrant_client
from app.medical.config import get_medical_config
from app.medical.embeddings import build_embeddings, get_embedding_dim

logger = logging.getLogger(__name__)


def _client() -> QdrantClient:
    cfg = get_medical_config().episodic
    return build_qdrant_client(
        vector_local_path=cfg.vector_local_path,
        url=cfg.url,
        api_key=cfg.api_key,
    )


def _collection_name() -> str:
    return get_medical_config().episodic.collection_name


def _point_id(session_id: str) -> str:
    return str(uuid.uuid5(uuid.NAMESPACE_URL, f"helios-session-memory:{session_id}"))


def _ensure_collection(client: QdrantClient, collection: str) -> None:
    if client.collection_exists(collection):
        return
    client.create_collection(
        collection_name=collection,
        vectors_config=VectorParams(size=get_embedding_dim(), distance=Distance.COSINE),
    )
    # Qdrant Cloud requires payload indexes for filtered search/delete.
    for field in ("user_id", "session_id"):
        try:
            client.create_payload_index(
                collection_name=collection,
                field_name=field,
                field_schema=PayloadSchemaType.KEYWORD,
            )
        except Exception as exc:  # noqa: BLE001
            logger.warning("episodic payload index %s creation failed: %s", field, exc)


def _upsert_point(
    *,
    session_id: str,
    user_id: str,
    text: str,
    started_at: datetime,
) -> None:
    client = _client()
    collection = _collection_name()
    _ensure_collection(client, collection)
    vector = build_embeddings().embed_query(text)
    client.upsert(
        collection_name=collection,
        points=[
            PointStruct(
                id=_point_id(session_id),
                vector=vector,
                payload={
                    "session_id": session_id,
                    "user_id": user_id,
                    "started_at_ts": started_at.timestamp(),
                },
            )
        ],
    )


def _delete_points(session_id: str) -> None:
    client = _client()
    collection = _collection_name()
    if not client.collection_exists(collection):
        return
    client.delete(
        collection_name=collection,
        points_selector=PointIdsList(points=[_point_id(session_id)]),
    )
    try:
        # Safety sweep for any stray points; needs the session_id payload index.
        client.delete(
            collection_name=collection,
            points_selector=Filter(
                must=[FieldCondition(key="session_id", match=MatchValue(value=session_id))]
            ),
        )
    except Exception as exc:  # noqa: BLE001 — the id-based delete above already ran
        logger.warning("episodic filter-delete sweep failed: %s", exc)


def _search_points(
    *,
    user_id: str,
    query_text: str,
    limit: int,
) -> list[tuple[str, float, float]]:
    """Return (session_id, cosine_score, started_at_ts) for one user's sessions."""
    client = _client()
    collection = _collection_name()
    if not client.collection_exists(collection):
        return []
    vector = build_embeddings().embed_query(query_text)
    response = client.query_points(
        collection_name=collection,
        query=vector,
        limit=limit,
        with_payload=True,
        query_filter=Filter(
            must=[FieldCondition(key="user_id", match=MatchValue(value=user_id))]
        ),
    )
    out: list[tuple[str, float, float]] = []
    for hit in response.points:
        payload = hit.payload or {}
        sid = str(payload.get("session_id") or "")
        if not sid:
            continue
        out.append((sid, float(hit.score or 0.0), float(payload.get("started_at_ts") or 0.0)))
    return out


# ---------------------------------------------------------------------------
# Write path: finalize a session into episodic memory
# ---------------------------------------------------------------------------


async def finalize_session_memory(
    db: Any,
    redis: Any,
    *,
    session_id: str,
    reason: str = "session_end",
) -> bool:
    """Flush the rolling summary and persist this session as one episodic record.

    Idempotent: skipped when no new user turns arrived since the last
    extraction, so calling it on every new-session start is cheap.
    """
    from app.auth.repository import resolve_user_id_for_session
    from app.conversation.summary import maybe_consolidate_summary
    from app.db.repository import (
        count_user_messages,
        get_conversation_by_session,
        mark_conversation_memory_extracted,
        upsert_session_memory,
    )

    if not get_settings().enable_episodic_memory:
        return False

    conv = await get_conversation_by_session(db, session_id)
    if not conv:
        return False
    cid = conv.get("_id")
    if not isinstance(cid, ObjectId):
        return False

    user_id = await resolve_user_id_for_session(db, session_id)
    if user_id is None:
        return False  # anonymous sessions carry no cross-session memory

    total = await count_user_messages(db, cid)
    extracted = int(conv.get("memory_extracted_turns") or 0)
    if total <= 0 or total <= extracted:
        return False
    if total < get_settings().episodic_memory_min_turns:
        return False  # single vague questions would pollute retrieval

    summary = await maybe_consolidate_summary(
        db,
        redis,
        session_id=session_id,
        conversation_id=cid,
        force=True,
    )
    if not summary.strip():
        return False

    title = str(conv.get("title") or "").strip()
    started_at = conv.get("created_at")
    if not isinstance(started_at, datetime):
        started_at = datetime.now(UTC)

    await upsert_session_memory(
        db,
        session_id=session_id,
        user_id=user_id,
        conversation_id=cid,
        title=title,
        summary_md=summary,
        session_started_at=started_at,
        source=reason,
    )
    await asyncio.to_thread(
        _upsert_point,
        session_id=session_id,
        user_id=str(user_id),
        text=f"{title}\n{summary}".strip(),
        started_at=started_at,
    )
    await mark_conversation_memory_extracted(db, cid, extracted_turns=total)
    logger.info(
        "episodic memory saved: session=%s user=%s turns=%d reason=%s",
        session_id,
        user_id,
        total,
        reason,
    )
    return True


def schedule_finalize_session_memory(
    db: Any,
    redis: Any,
    *,
    session_id: str,
    reason: str = "session_end",
) -> None:
    """Fire-and-forget wrapper around finalize_session_memory."""

    async def _run() -> None:
        try:
            await finalize_session_memory(db, redis, session_id=session_id, reason=reason)
        except Exception as exc:  # noqa: BLE001
            logger.warning("episodic memory finalize failed (non-critical): %s", exc)

    asyncio.create_task(_run())


async def finalize_previous_sessions(
    db: Any,
    redis: Any,
    *,
    user_id: ObjectId,
    exclude_session_id: str,
    limit: int = 3,
) -> int:
    """Lazy consolidation: when a user opens a new session, finalize recent
    earlier ones that still have un-extracted turns. Returns #finalized."""
    from app.db.repository import get_support_mode, list_conversations_for_user

    finalized = 0
    convs = await list_conversations_for_user(db, user_id=user_id, limit=limit + 1)
    for conv in convs:
        sid = str(conv.get("session_id") or "")
        if not sid or sid == exclude_session_id:
            continue
        if get_support_mode(conv) == "human":
            continue  # still live with a counselor; finalized on leave
        if await finalize_session_memory(db, redis, session_id=sid, reason="new_session"):
            finalized += 1
    return finalized


def schedule_finalize_previous_sessions(
    db: Any,
    redis: Any,
    *,
    user_id: ObjectId,
    exclude_session_id: str,
    limit: int = 3,
) -> None:
    """Fire-and-forget wrapper around finalize_previous_sessions."""

    async def _run() -> None:
        try:
            await finalize_previous_sessions(
                db,
                redis,
                user_id=user_id,
                exclude_session_id=exclude_session_id,
                limit=limit,
            )
        except Exception as exc:  # noqa: BLE001
            logger.warning("previous-session finalize failed (non-critical): %s", exc)

    asyncio.create_task(_run())


async def delete_session_memory(db: Any, *, session_id: str) -> None:
    """Cascade removal (Mongo record + Qdrant point) when a conversation is deleted."""
    from app.db.repository import delete_session_memory_record

    try:
        await delete_session_memory_record(db, session_id=session_id)
        await asyncio.to_thread(_delete_points, session_id)
    except Exception as exc:  # noqa: BLE001
        logger.warning("episodic memory delete failed (non-critical): %s", exc)


# ---------------------------------------------------------------------------
# Read path: retrieve relevant past sessions for the current turn
# ---------------------------------------------------------------------------


def _recency_boost(started_at_ts: float, *, now_ts: float) -> float:
    settings = get_settings()
    if started_at_ts <= 0:
        return 0.0
    age_days = max(0.0, (now_ts - started_at_ts) / 86400.0)
    half_life = settings.episodic_memory_recency_half_life_days
    return settings.episodic_memory_recency_weight * math.exp(-age_days / half_life)


def _trim(text: str, max_chars: int = 700) -> str:
    text = text.strip()
    if len(text) <= max_chars:
        return text
    return text[: max_chars - 3].rstrip() + "..."


# Recency-prior fallback: with no strong semantic match (e.g. a terse first
# message like "sinh viên thì sao?"), the user is most likely continuing their
# latest session — include it at a relaxed threshold while it is still fresh.
_FALLBACK_SCORE_RATIO = 0.5
_FALLBACK_MAX_AGE_DAYS = 14.0


async def retrieve_relevant_session_memories(
    db: Any,
    *,
    user_id: ObjectId,
    query_text: str,
    exclude_session_id: str | None = None,
    top_k: int | None = None,
    min_score: float | None = None,
    fallback_most_recent: bool = False,
) -> str:
    """Markdown block of the past sessions most relevant to the current turn.

    Returns "" when episodic memory is disabled, the user has no stored
    sessions, or nothing clears the relevance threshold — the agent prompt
    then shows its usual "(none yet)" placeholder. With
    ``fallback_most_recent=True`` (early turns of a new session), the most
    recent session is included at a relaxed threshold when nothing else hits.
    """
    from app.db.repository import get_session_memories_by_session_ids

    settings = get_settings()
    if not settings.enable_episodic_memory:
        return ""
    query = (query_text or "").strip()
    if not query:
        return ""

    k = top_k or settings.episodic_memory_top_k
    threshold = settings.episodic_memory_min_score if min_score is None else min_score

    try:
        hits = await asyncio.to_thread(
            _search_points,
            user_id=str(user_id),
            query_text=query,
            limit=max(k * 3, k + 2),
        )
    except Exception as exc:  # noqa: BLE001
        logger.warning("episodic memory search failed (non-critical): %s", exc)
        return ""

    now_ts = datetime.now(UTC).timestamp()
    candidates = [
        (sid, score, started_ts)
        for sid, score, started_ts in hits
        if not (exclude_session_id and sid == exclude_session_id)
    ]

    # (session_id, relevance, combined, is_fallback)
    ranked: list[tuple[str, float, float, bool]] = [
        (sid, score, score + _recency_boost(started_ts, now_ts=now_ts), False)
        for sid, score, started_ts in candidates
        if score >= threshold
    ]
    ranked.sort(key=lambda row: -row[2])
    ranked = ranked[:k]

    used_fallback = False
    if not ranked and fallback_most_recent and candidates:
        newest = max(candidates, key=lambda row: row[2])
        sid, score, started_ts = newest
        age_days = (now_ts - started_ts) / 86400.0 if started_ts > 0 else None
        if (
            score >= threshold * _FALLBACK_SCORE_RATIO
            and age_days is not None
            and age_days <= _FALLBACK_MAX_AGE_DAYS
        ):
            ranked = [(sid, score, score, True)]
            used_fallback = True

    top_score = max((score for _, score, _ in candidates), default=0.0)
    logger.info(
        "episodic retrieval: user=%s hits=%d top=%.3f threshold=%.2f kept=%d fallback=%s",
        user_id,
        len(candidates),
        top_score,
        threshold,
        len(ranked),
        used_fallback,
    )
    if not ranked:
        return ""

    docs = await get_session_memories_by_session_ids(
        db,
        user_id=user_id,
        session_ids=[sid for sid, _, _, _ in ranked],
    )
    by_sid = {str(d.get("session_id")): d for d in docs}

    sections: list[str] = []
    for sid, relevance, _, is_fallback in ranked:
        doc = by_sid.get(sid)
        if not doc:
            continue
        title = str(doc.get("title") or "").strip() or "(không có tiêu đề)"
        started = doc.get("session_started_at")
        date_str = started.strftime("%Y-%m-%d") if isinstance(started, datetime) else "?"
        summary_md = _trim(str(doc.get("summary_md") or ""))
        note = (
            f"phiên gần nhất — độ liên quan thấp {relevance:.2f}, dùng thận trọng"
            if is_fallback
            else f"độ liên quan {relevance:.2f}"
        )
        sections.append(f"### Phiên {date_str} — {title} ({note})\n{summary_md}")

    return "\n\n".join(sections)
