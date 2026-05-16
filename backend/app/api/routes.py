from __future__ import annotations

import asyncio
from datetime import UTC, datetime
from typing import Any

from bson import ObjectId
from fastapi import APIRouter, HTTPException, Request
from pydantic import BaseModel, Field

from app.config import ProviderName
from app.db.repository import (
    add_activity_completion,
    append_message,
    create_conversation,
    get_conversation_by_session,
    list_activity_completions,
    list_messages_chronological,
)
from app.graph.safety_engine import (
    CRISIS_CHOICES_VI,
    CRISIS_REPLY_VI,
    run_safety_engine,
)
from app.graph.nodes.response_generator import is_meta_conversation
from app.graph.workflow import run_turn
from app.llm.factory import default_provider, resolve_provider
from app.wellness.suggestions import align_assistant_reply_with_suggestions, detect_suggested_activities_llm

router = APIRouter(prefix="/api/v1")


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def get_db(request: Request):
    db = getattr(request.app.state, "db", None)
    if db is None:
        raise HTTPException(503, "Database not ready")
    return db


def get_redis(request: Request):
    return getattr(request.app.state, "redis", None)


# ---------------------------------------------------------------------------
# Models
# ---------------------------------------------------------------------------

class ConversationSummary(BaseModel):
    session_id: str
    title: str
    updated_at: str


class ChatRequest(BaseModel):
    message: str = Field(..., min_length=1, max_length=8000)
    session_id: str = Field(..., min_length=8, max_length=128)
    provider: str | None = None


class ActivitySuggestionOut(BaseModel):
    id: str
    title: str
    description: str


class ChatResponse(BaseModel):
    reply: str
    session_id: str
    conversation_id: str
    assistant_message_id: str | None = None
    provider: str
    # Safety / routing
    chat_blocked: bool = False
    crisis_choices: list[str] = Field(default_factory=list)
    message_type: str = "normal"       # "normal" | "off_topic" | "crisis"
    # Emotion / therapy metadata
    emotion: str | None = None
    therapy_strategy: str | None = None
    # Wellness activities
    suggested_activities: list[ActivitySuggestionOut] = Field(default_factory=list)
    metadata: dict[str, Any] | None = None


# ---------------------------------------------------------------------------
# Chat endpoint
# ---------------------------------------------------------------------------

@router.post("/chat", response_model=ChatResponse)
async def chat(req: ChatRequest, request: Request) -> ChatResponse:
    from app.cache.session_memory import get_turns, push_turn
    from app.graph.nodes.memory_update import run_memory_update

    db = get_db(request)
    redis = get_redis(request)

    # Ensure conversation exists in MongoDB (persistent store)
    conv = await get_conversation_by_session(db, req.session_id)
    if not conv:
        conv = await create_conversation(db, session_id=req.session_id)
    cid = conv["_id"]
    assert isinstance(cid, ObjectId)

    # Persist user message to MongoDB
    await append_message(db, conversation_id=cid, role="user", content=req.message)

    # Short-term history from Redis (fast); push user turn
    if redis is not None:
        await push_turn(redis, req.session_id, "user", req.message)
        history = await get_turns(redis, req.session_id, limit=20)
        # Exclude the turn we just pushed (the last one) so history = prior context
        history = history[:-1]
    else:
        # Fallback: not using Redis (dev without cache)
        history = []

    default_p: ProviderName = default_provider()
    provider: ProviderName = resolve_provider(req.provider, default=default_p)

    # -----------------------------------------------------------------------
    # Parallel: safety engine + main LangGraph graph
    # Pattern from QueryWeaver: asyncio.create_task for both, then gather
    # -----------------------------------------------------------------------
    graph_state: dict[str, Any] = {
        "user_input": req.message,
        "history": history,
        "provider": provider,
        "session_id": req.session_id,
        "db": db,
    }

    safety_task = asyncio.create_task(
        run_safety_engine(req.message, history, provider)
    )
    main_task = asyncio.create_task(run_turn(graph_state))

    safety_result, graph_out = await asyncio.gather(safety_task, main_task)

    # -----------------------------------------------------------------------
    # Merge: safety overrides if emergency
    # -----------------------------------------------------------------------
    if safety_result["emergency_mode"]:
        reply = CRISIS_REPLY_VI
        chat_blocked = True
        crisis_choices = CRISIS_CHOICES_VI
        message_type = "crisis"
        suggested_activities: list[dict[str, Any]] = []
        emotion = graph_out.get("primary_emotion")
        therapy_strategy = None
        meta_out: dict[str, Any] = {
            "risk_level": safety_result["risk_level"],
            "safety_confidence": safety_result["confidence"],
            "safety_triggers": safety_result["triggers"],
        }
    else:
        reply = str(graph_out.get("final_reply") or "").strip()
        if not reply:
            reply = "Mình ở đây với bạn. Bạn có thể chia sẻ thêm không?"
        chat_blocked = False
        crisis_choices = []
        message_type = str(graph_out.get("message_type") or "normal")
        emotion = graph_out.get("primary_emotion")
        therapy_strategy = graph_out.get("therapy_strategy")

        # Wellness activity suggestions — only when therapeutically relevant.
        # Skip for: casual/greetings, off_topic, stabilization (severe distress),
        # and reflective_listening on first exchange.
        _intent = str(graph_out.get("intent") or "")
        _strategy = str(therapy_strategy or "")
        _skip_wellness = (
            message_type != "normal"
            or _intent == "casual"
            or _strategy == "stabilization"
            or is_meta_conversation(req.message)
        )
        if not _skip_wellness:
            recent_user_blob = req.message
            suggested_activities = await detect_suggested_activities_llm(
                user_input=req.message,
                assistant_reply=reply,
                risk_level="low",
                provider=provider,
                recent_user_messages=recent_user_blob,
            )
            reply = align_assistant_reply_with_suggestions(reply, suggested_activities)
        else:
            suggested_activities = []

        meta_out = {
            "risk_level": safety_result["risk_level"],
            "safety_confidence": safety_result["confidence"],
            "emotion": emotion,
            "intent": _intent,
            "therapy_strategy": therapy_strategy,
            "suggested_activities": suggested_activities,
            **(graph_out.get("metadata") or {}),
        }

    # Persist assistant message to MongoDB
    assistant_doc = await append_message(
        db,
        conversation_id=cid,
        role="assistant",
        content=reply,
        metadata={
            "message_type": message_type,
            "chat_blocked": chat_blocked,
            "crisis_choices": crisis_choices,
            **meta_out,
        },
    )
    aid = assistant_doc.get("_id")
    assistant_message_id = str(aid) if aid is not None else None

    # Push assistant turn to Redis short-term memory
    if redis is not None:
        await push_turn(redis, req.session_id, "assistant", reply)

    # Background: update long-term user profile (non-blocking)
    if not chat_blocked and message_type == "normal":
        asyncio.create_task(
            run_memory_update(db, req.session_id, req.message, reply, provider)
        )

    return ChatResponse(
        reply=reply,
        session_id=req.session_id,
        conversation_id=str(cid),
        assistant_message_id=assistant_message_id,
        provider=provider,
        chat_blocked=chat_blocked,
        crisis_choices=crisis_choices,
        message_type=message_type,
        emotion=emotion,
        therapy_strategy=therapy_strategy,
        suggested_activities=[ActivitySuggestionOut(**s) for s in suggested_activities],
        metadata=meta_out,
    )


# ---------------------------------------------------------------------------
# Conversations
# ---------------------------------------------------------------------------

@router.get("/conversations", response_model=list[ConversationSummary])
async def conversations(
    request: Request,
    session_id: str,
    limit: int = 30,
) -> list[ConversationSummary]:
    from app.db.repository import list_conversations

    db = get_db(request)
    rows = await list_conversations(db, session_id=session_id, limit=limit)
    out: list[ConversationSummary] = []
    for doc in rows:
        updated = doc.get("updated_at") or doc.get("created_at")
        updated_iso = (
            updated.replace(tzinfo=UTC).isoformat()
            if isinstance(updated, datetime)
            else str(updated)
        )
        out.append(
            ConversationSummary(
                session_id=doc["session_id"],
                title=str(doc.get("title") or "Chat"),
                updated_at=updated_iso,
            )
        )
    return out


# ---------------------------------------------------------------------------
# Mood
# ---------------------------------------------------------------------------

class MoodCreate(BaseModel):
    session_id: str = Field(..., min_length=8, max_length=128)
    score: int = Field(..., ge=1, le=10)
    note: str | None = Field(None, max_length=2000)


class MoodEntryOut(BaseModel):
    id: str
    session_id: str
    score: int
    note: str | None
    created_at: str


@router.post("/mood", response_model=MoodEntryOut)
async def create_mood(body: MoodCreate, request: Request) -> MoodEntryOut:
    from app.db.repository import add_mood_entry

    db = get_db(request)
    doc = await add_mood_entry(db, session_id=body.session_id, score=body.score, note=body.note)
    oid = doc["_id"]
    created = doc["created_at"]
    created_iso = (
        created.replace(tzinfo=UTC).isoformat()
        if isinstance(created, datetime)
        else str(created)
    )
    return MoodEntryOut(
        id=str(oid),
        session_id=body.session_id,
        score=body.score,
        note=body.note,
        created_at=created_iso,
    )


@router.get("/mood", response_model=list[MoodEntryOut])
async def list_mood(session_id: str, request: Request, limit: int = 60) -> list[MoodEntryOut]:
    from app.db.repository import list_mood_entries

    db = get_db(request)
    rows = await list_mood_entries(db, session_id=session_id, limit=limit)
    out: list[MoodEntryOut] = []
    for doc in rows:
        created = doc["created_at"]
        created_iso = (
            created.replace(tzinfo=UTC).isoformat()
            if isinstance(created, datetime)
            else str(created)
        )
        out.append(
            MoodEntryOut(
                id=str(doc["_id"]),
                session_id=doc["session_id"],
                score=int(doc["score"]),
                note=doc.get("note"),
                created_at=created_iso,
            )
        )
    return out


# ---------------------------------------------------------------------------
# Messages (history)
# ---------------------------------------------------------------------------

ALLOWED_ACTIVITY_IDS = frozenset({"breathing_box", "ocean_sound"})


class MessageOut(BaseModel):
    id: str
    role: str
    content: str
    created_at: str
    metadata: dict[str, Any] | None = None


@router.get("/messages", response_model=list[MessageOut])
async def list_messages(session_id: str, request: Request, limit: int = 100) -> list[MessageOut]:
    db = get_db(request)
    conv = await get_conversation_by_session(db, session_id)
    if not conv:
        return []
    cid = conv["_id"]
    assert isinstance(cid, ObjectId)
    rows = await list_messages_chronological(db, conversation_id=cid, limit=limit)
    out: list[MessageOut] = []
    for doc in rows:
        created = doc["created_at"]
        created_iso = (
            created.replace(tzinfo=UTC).isoformat()
            if isinstance(created, datetime)
            else str(created)
        )
        meta = doc.get("metadata")
        out.append(
            MessageOut(
                id=str(doc["_id"]),
                role=str(doc["role"]),
                content=str(doc["content"]),
                created_at=created_iso,
                metadata=meta if isinstance(meta, dict) else None,
            )
        )
    return out


# ---------------------------------------------------------------------------
# Activities
# ---------------------------------------------------------------------------

class ActivityCompleteBody(BaseModel):
    session_id: str = Field(..., min_length=8, max_length=128)
    activity_id: str = Field(..., min_length=2, max_length=64)
    linked_message_id: str | None = Field(None, max_length=32)
    duration_sec: int | None = Field(None, ge=1, le=86400)


class ActivityCompletionOut(BaseModel):
    id: str
    session_id: str
    activity_id: str
    linked_message_id: str | None
    created_at: str


@router.post("/activities/complete", response_model=ActivityCompletionOut)
async def complete_activity(body: ActivityCompleteBody, request: Request) -> ActivityCompletionOut:
    if body.activity_id not in ALLOWED_ACTIVITY_IDS:
        raise HTTPException(400, f"activity_id must be one of: {', '.join(sorted(ALLOWED_ACTIVITY_IDS))}")
    db = get_db(request)
    conv = await get_conversation_by_session(db, body.session_id)
    if not conv:
        conv = await create_conversation(db, session_id=body.session_id)
    cid = conv["_id"]
    assert isinstance(cid, ObjectId)
    link_oid: ObjectId | None = None
    if body.linked_message_id:
        try:
            link_oid = ObjectId(body.linked_message_id)
        except Exception as exc:  # noqa: BLE001
            raise HTTPException(400, "Invalid linked_message_id") from exc
    doc = await add_activity_completion(
        db,
        session_id=body.session_id,
        conversation_id=cid,
        activity_id=body.activity_id,
        linked_message_id=link_oid,
        duration_sec=body.duration_sec,
    )
    created = doc["created_at"]
    created_iso = (
        created.replace(tzinfo=UTC).isoformat()
        if isinstance(created, datetime)
        else str(created)
    )
    lid = doc.get("linked_message_id")
    return ActivityCompletionOut(
        id=str(doc["_id"]),
        session_id=body.session_id,
        activity_id=body.activity_id,
        linked_message_id=str(lid) if lid is not None else None,
        created_at=created_iso,
    )


@router.get("/activities", response_model=list[ActivityCompletionOut])
async def list_activities(session_id: str, request: Request, limit: int = 100) -> list[ActivityCompletionOut]:
    db = get_db(request)
    rows = await list_activity_completions(db, session_id=session_id, limit=limit)
    out: list[ActivityCompletionOut] = []
    for doc in rows:
        created = doc["created_at"]
        created_iso = (
            created.replace(tzinfo=UTC).isoformat()
            if isinstance(created, datetime)
            else str(created)
        )
        lid = doc.get("linked_message_id")
        out.append(
            ActivityCompletionOut(
                id=str(doc["_id"]),
                session_id=doc["session_id"],
                activity_id=str(doc["activity_id"]),
                linked_message_id=str(lid) if lid is not None else None,
                created_at=created_iso,
            )
        )
    return out
