from __future__ import annotations

import asyncio
import json
from datetime import UTC, datetime
from typing import Any

from bson import ObjectId
from fastapi import APIRouter, File, Form, HTTPException, Request, UploadFile
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, Field

from app.auth.dependencies import resolve_optional_current_user
from app.auth.repository import link_session_to_user
from app.db.repository import (
    ACTIVITY_COMPLETIONS,
    add_activity_completion,
    append_message,
    create_conversation,
    get_conversation_by_session,
    get_support_mode,
    list_activity_completions,
    list_messages_for_user,
)
from app.llm.factory import default_provider

router = APIRouter(prefix="/api/v1")

CHAT_MODE = "medical"


def get_db(request: Request):
    db = getattr(request.app.state, "db", None)
    if db is None:
        raise HTTPException(503, "Database not ready")
    return db


def get_redis(request: Request):
    return getattr(request.app.state, "redis", None)


class ConversationSummary(BaseModel):
    session_id: str
    title: str
    updated_at: str
    chat_mode: str = CHAT_MODE
    summary: str | None = None
    summary_updated_at: str | None = None


class ChatRequest(BaseModel):
    message: str = Field(..., min_length=1, max_length=8000)
    session_id: str = Field(..., min_length=8, max_length=128)


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
    message_type: str = "medical"
    suggested_activities: list[ActivitySuggestionOut] = Field(default_factory=list)
    metadata: dict[str, Any] | None = None
    support_mode: str = "ai"
    assigned_support_name: str | None = None


class HandoffRequestBody(BaseModel):
    session_id: str = Field(..., min_length=8, max_length=128)
    confirm: bool = False


class ConversationStatusOut(BaseModel):
    session_id: str
    support_mode: str
    assigned_support_name: str | None = None
    assigned_support_id: str | None = None


class WellnessStartRequest(BaseModel):
    session_id: str = Field(..., min_length=8, max_length=128)
    activity_id: str = Field(..., min_length=2, max_length=64)
    quiet: bool = False
    lang: str | None = Field(None, pattern="^(vi|en)$")


class WellnessCompleteRequest(BaseModel):
    session_id: str = Field(..., min_length=8, max_length=128)
    lang: str | None = Field(None, pattern="^(vi|en)$")
    activity_id: str | None = Field(None, min_length=2, max_length=64)
    duration_sec: int | None = Field(None, ge=1, le=86400)


@router.post("/chat", response_model=ChatResponse)
async def chat(req: ChatRequest, request: Request) -> ChatResponse:
    return await _execute_chat(req, request)


async def _execute_chat(req: ChatRequest, request: Request) -> ChatResponse:
    from app.api.medical_handlers import handle_medical_chat_turn, resolve_conversation
    from app.chat_progress import emit_progress
    from app.conversation.context import load_conversation_summary
    from app.conversation.summary import schedule_conversation_summary_update
    from app.conversation.title import generate_conversation_title
    from app.db.repository import count_user_messages, update_conversation_title
    from app.handoff.messages import CLOSED_SESSION_NOTICE, handoff_ack

    db = get_db(request)
    redis = get_redis(request)
    maybe_user = await resolve_optional_current_user(request, db)
    uid: ObjectId | None = None
    if maybe_user:
        raw_uid = maybe_user.get("_id")
        if isinstance(raw_uid, ObjectId):
            uid = raw_uid

    emit_progress("analyzing_request")

    conv = await get_conversation_by_session(db, req.session_id)
    conv = await resolve_conversation(
        db,
        session_id=req.session_id,
        conv=conv,
        user_id=uid,
    )
    if uid is not None:
        await link_session_to_user(db, session_id=req.session_id, user_id=uid)
    cid = conv["_id"]
    assert isinstance(cid, ObjectId)

    support_mode = get_support_mode(conv)
    assigned_support_name = conv.get("assigned_support_name")

    if support_mode == "human":
        raise HTTPException(
            409,
            detail="Session is in human support mode. Send messages via WebSocket.",
        )
    if support_mode == "closed":
        raise HTTPException(403, detail=CLOSED_SESSION_NOTICE["vi"])

    await append_message(
        db,
        conversation_id=cid,
        role="user",
        content=req.message,
        metadata={"chat_mode": CHAT_MODE, "visibility": "all"},
    )

    if support_mode == "awaiting_support":
        ack = handoff_ack("vi")
        meta = {
            "chat_mode": CHAT_MODE,
            "agent_name": "HUMAN_HANDOFF",
            "message_type": "medical",
            "sender_name": "Helios",
            "visibility": "all",
        }
        assistant_doc = await append_message(
            db,
            conversation_id=cid,
            role="assistant",
            content=ack,
            metadata=meta,
        )
        aid = assistant_doc.get("_id")
        return ChatResponse(
            reply=ack,
            session_id=req.session_id,
            conversation_id=str(cid),
            assistant_message_id=str(aid) if aid else None,
            provider=default_provider(),
            message_type="medical",
            metadata=meta,
            support_mode="awaiting_support",
            assigned_support_name=assigned_support_name,
        )

    user_turn_count = await count_user_messages(db, cid)
    default_titles = {"New chat", "Chat", ""}
    current_title = str(conv.get("title") or "")
    if user_turn_count == 1 and current_title in default_titles:

        async def _set_title() -> None:
            title = await generate_conversation_title(
                req.message,
                provider=default_provider(),
            )
            await update_conversation_title(db, cid, title)

        asyncio.create_task(_set_title())
    medical_provider = default_provider()
    conversation_summary = await load_conversation_summary(db, redis, req.session_id)
    reply, meta, assistant_message_id = await handle_medical_chat_turn(
        db,
        session_id=req.session_id,
        conversation_id=cid,
        message=req.message,
        conversation_summary=conversation_summary,
    )
    suggested = meta.get("suggested_activities") or []

    if meta.get("agent_name") != "HUMAN_HANDOFF":
        schedule_conversation_summary_update(
            db,
            redis,
            session_id=req.session_id,
            conversation_id=cid,
            user_message=req.message,
            assistant_reply=reply,
            provider=medical_provider,
        )

    return ChatResponse(
        reply=reply,
        session_id=req.session_id,
        conversation_id=str(cid),
        assistant_message_id=assistant_message_id,
        provider=medical_provider,
        message_type="medical",
        suggested_activities=[ActivitySuggestionOut(**s) for s in suggested],
        metadata=meta,
        support_mode=support_mode,
        assigned_support_name=assigned_support_name,
    )


@router.post("/handoff/request", response_model=ChatResponse)
async def request_handoff(body: HandoffRequestBody, request: Request) -> ChatResponse:
    from app.api.medical_handlers import resolve_conversation
    from app.handoff.escalate import escalate_to_awaiting_support
    from app.handoff.messages import handoff_ack, handoff_consent_notice

    db = get_db(request)
    redis = get_redis(request)
    conv = await get_conversation_by_session(db, body.session_id)
    conv = await resolve_conversation(db, session_id=body.session_id, conv=conv)
    cid = conv["_id"]
    assert isinstance(cid, ObjectId)

    support_mode = get_support_mode(conv)
    if support_mode in ("awaiting_support", "human"):
        ack = handoff_ack("vi")
        return ChatResponse(
            reply=ack,
            session_id=body.session_id,
            conversation_id=str(cid),
            provider=default_provider(),
            support_mode=support_mode,
            assigned_support_name=conv.get("assigned_support_name"),
        )

    if not body.confirm:
        consent = handoff_consent_notice("vi")
        meta = {
            "chat_mode": CHAT_MODE,
            "agent_name": "HUMAN_HANDOFF",
            "message_type": "medical",
            "sender_name": "Helios",
            "visibility": "all",
            "handoff_consent_prompt": True,
        }
        assistant_doc = await append_message(
            db,
            conversation_id=cid,
            role="assistant",
            content=consent,
            metadata=meta,
        )
        aid = assistant_doc.get("_id")
        return ChatResponse(
            reply=consent,
            session_id=body.session_id,
            conversation_id=str(cid),
            assistant_message_id=str(aid) if aid else None,
            provider=default_provider(),
            metadata=meta,
            support_mode="ai",
        )

    await escalate_to_awaiting_support(
        db,
        redis,
        conversation_id=cid,
        session_id=body.session_id,
        source="button",
    )
    ack = handoff_ack("vi")
    meta = {
        "chat_mode": CHAT_MODE,
        "agent_name": "HUMAN_HANDOFF",
        "message_type": "medical",
        "sender_name": "Helios",
        "visibility": "all",
        "handoff_confirmed": True,
    }
    assistant_doc = await append_message(
        db,
        conversation_id=cid,
        role="assistant",
        content=ack,
        metadata=meta,
    )
    aid = assistant_doc.get("_id")
    return ChatResponse(
        reply=ack,
        session_id=body.session_id,
        conversation_id=str(cid),
        assistant_message_id=str(aid) if aid else None,
        provider=default_provider(),
        metadata=meta,
        support_mode="awaiting_support",
    )


@router.get("/conversations/{session_id}/status", response_model=ConversationStatusOut)
async def conversation_status(session_id: str, request: Request) -> ConversationStatusOut:
    db = get_db(request)
    conv = await get_conversation_by_session(db, session_id)
    if not conv:
        return ConversationStatusOut(session_id=session_id, support_mode="ai")
    assigned = conv.get("assigned_support_id")
    return ConversationStatusOut(
        session_id=session_id,
        support_mode=get_support_mode(conv),
        assigned_support_name=conv.get("assigned_support_name"),
        assigned_support_id=str(assigned) if isinstance(assigned, ObjectId) else None,
    )


def _json_default(obj: Any) -> Any:
    if isinstance(obj, ObjectId):
        return str(obj)
    raise TypeError(f"Object of type {type(obj).__name__} is not JSON serializable")


@router.post("/chat/stream")
async def chat_stream(req: ChatRequest, request: Request) -> StreamingResponse:
    """SSE stream: status steps while processing, then final ChatResponse JSON."""
    from app.chat_progress import (
        label_for_step,
        reset_progress_callback,
        set_progress_callback,
        set_thread_progress_callback,
    )

    lang = "vi"

    async def event_generator():
        loop = asyncio.get_running_loop()
        progress_queue: asyncio.Queue[str] = asyncio.Queue()
        last_step: list[str | None] = [None]

        def _enqueue(step: str) -> None:
            if step == last_step[0]:
                return
            last_step[0] = step
            progress_queue.put_nowait(step)

        def on_progress(step: str) -> None:
            loop.call_soon_threadsafe(_enqueue, step)

        def _status_sse(step: str) -> str:
            payload = {
                "type": "status",
                "step": step,
                "label": label_for_step(step, lang),
            }
            return f"data: {json.dumps(payload, ensure_ascii=False)}\n\n"

        token = set_progress_callback(on_progress)
        set_thread_progress_callback(on_progress)
        chat_task = asyncio.create_task(_execute_chat(req, request))

        try:
            yield ": " + " " * 2048 + "\n\n"

            while True:
                while not progress_queue.empty():
                    yield _status_sse(progress_queue.get_nowait())
                    await asyncio.sleep(0)

                if chat_task.done():
                    break

                try:
                    step = await asyncio.wait_for(progress_queue.get(), timeout=0.08)
                    yield _status_sse(step)
                    await asyncio.sleep(0)
                except asyncio.TimeoutError:
                    continue

            while not progress_queue.empty():
                yield _status_sse(progress_queue.get_nowait())
                await asyncio.sleep(0)

            result = await chat_task
            done_payload = {
                "type": "done",
                "reply": result.reply,
                "session_id": result.session_id,
                "conversation_id": result.conversation_id,
                "assistant_message_id": result.assistant_message_id,
                "provider": result.provider,
                "message_type": result.message_type,
                "suggested_activities": [s.model_dump() for s in result.suggested_activities],
                "metadata": result.metadata,
                "support_mode": result.support_mode,
                "assigned_support_name": result.assigned_support_name,
            }
            yield f"data: {json.dumps(done_payload, ensure_ascii=False, default=_json_default)}\n\n"
        except Exception as exc:
            err = {"type": "error", "message": str(exc)}
            yield f"data: {json.dumps(err, ensure_ascii=False)}\n\n"
        finally:
            set_thread_progress_callback(None)
            reset_progress_callback(token)

    return StreamingResponse(
        event_generator(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache, no-transform",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",
        },
    )


@router.post("/wellness/start", response_model=ChatResponse)
async def wellness_start(body: WellnessStartRequest, request: Request) -> ChatResponse:
    from app.db.repository import is_valid_activity_id
    from app.wellness.session import set_active, start_session

    db = get_db(request)
    redis = get_redis(request)
    if not await is_valid_activity_id(db, body.activity_id):
        raise HTTPException(400, detail=f"Unknown or unavailable activity: {body.activity_id}")

    conv = await get_conversation_by_session(db, body.session_id)
    if not conv:
        conv = await create_conversation(db, session_id=body.session_id, chat_mode=CHAT_MODE)
    cid = conv["_id"]
    assert isinstance(cid, ObjectId)

    lang = body.lang if body.lang in ("vi", "en") else "vi"
    _, intro = await start_session(redis, session_id=body.session_id, activity_id=body.activity_id, lang=lang)
    await set_active(redis, body.session_id)

    meta_out: dict[str, Any] = {
        "wellness_session": {"activity_id": body.activity_id, "step": "active"},
        "chat_mode": CHAT_MODE,
    }
    aid: ObjectId | None = None
    if not body.quiet and intro:
        assistant_doc = await append_message(
            db,
            conversation_id=cid,
            role="assistant",
            content=intro,
            metadata=meta_out,
        )
        raw_aid = assistant_doc.get("_id")
        if isinstance(raw_aid, ObjectId):
            aid = raw_aid

    return ChatResponse(
        reply="" if body.quiet else intro,
        session_id=body.session_id,
        conversation_id=str(cid),
        assistant_message_id=str(aid) if aid else None,
        provider=default_provider(),
        suggested_activities=[],
        metadata=meta_out,
    )


@router.post("/wellness/complete")
async def wellness_complete(body: WellnessCompleteRequest, request: Request) -> dict[str, Any]:
    from app.wellness.session import clear_session, complete_session, get_session

    db = get_db(request)
    redis = get_redis(request)
    lang = body.lang if body.lang in ("vi", "en") else "vi"
    prior = await get_session(redis, body.session_id)
    activity_id = body.activity_id or (prior or {}).get("activity_id") or ""
    state, checkin_msg = await complete_session(redis, session_id=body.session_id, lang=lang)

    completion_id: str | None = None
    assistant_message_id: str | None = None
    if activity_id:
        conv = await get_conversation_by_session(db, body.session_id)
        if conv:
            cid = conv["_id"]
            assert isinstance(cid, ObjectId)
            doc = await add_activity_completion(
                db,
                session_id=body.session_id,
                conversation_id=cid,
                activity_id=str(activity_id),
                duration_sec=body.duration_sec,
                chat_mode=CHAT_MODE,
            )
            completion_id = str(doc["_id"])

    show_rating = bool(completion_id and activity_id)
    if show_rating or checkin_msg:
        conv = await get_conversation_by_session(db, body.session_id)
        if conv:
            cid = conv["_id"]
            assert isinstance(cid, ObjectId)
            meta: dict[str, Any] = {"chat_mode": CHAT_MODE}
            if show_rating:
                meta["pending_activity_rating"] = {
                    "activity_id": str(activity_id),
                    "completion_id": completion_id,
                    "rated": False,
                }
            content = checkin_msg or "Bạn vừa hoàn thành bài tập. Bạn đánh giá thế nào?"
            msg_doc = await append_message(
                db,
                conversation_id=cid,
                role="assistant",
                content=content,
                metadata=meta,
            )
            raw_mid = msg_doc.get("_id")
            if isinstance(raw_mid, ObjectId):
                assistant_message_id = str(raw_mid)
                if completion_id:
                    await db[ACTIVITY_COMPLETIONS].update_one(
                        {"_id": ObjectId(completion_id)},
                        {"$set": {"linked_message_id": raw_mid}},
                    )

    await clear_session(redis, body.session_id)
    return {
        "checkin_message": checkin_msg,
        "show_activity_rating": show_rating,
        "activity_id": activity_id or None,
        "completion_id": completion_id,
        "assistant_message_id": assistant_message_id,
        "wellness_session": state,
    }


@router.get("/conversations", response_model=list[ConversationSummary])
async def conversations(
    request: Request,
    session_id: str | None = None,
    session_ids: str | None = None,
    limit: int = 30,
) -> list[ConversationSummary]:
    from app.auth.repository import is_session_owned_by_user
    from app.db.repository import (
        list_conversations_by_session_ids,
        list_conversations_for_user,
    )

    db = get_db(request)
    maybe_user = await resolve_optional_current_user(request, db)
    uid: ObjectId | None = None
    if maybe_user:
        raw_uid = maybe_user.get("_id")
        if isinstance(raw_uid, ObjectId):
            uid = raw_uid

    rows: list[dict[str, Any]] = []
    seen_sids: set[str] = set()

    def _append_rows(docs: list[dict[str, Any]]) -> None:
        for doc in docs:
            sid = str(doc.get("session_id") or "")
            if sid and sid not in seen_sids:
                seen_sids.add(sid)
                rows.append(doc)

    if uid is not None:
        _append_rows(await list_conversations_for_user(db, user_id=uid, limit=limit))

    ids: list[str] = []
    if session_ids:
        ids = [s.strip() for s in session_ids.split(",") if s.strip()]
    elif session_id:
        ids = [session_id]
    if ids:
        extra = await list_conversations_by_session_ids(db, session_ids=ids, limit=limit)
        if uid is None:
            _append_rows(extra)
        else:
            for doc in extra:
                sid = str(doc.get("session_id") or "")
                if not sid or sid in seen_sids:
                    continue
                owner = doc.get("user_id")
                if owner == uid or await is_session_owned_by_user(
                    db, session_id=sid, user_id=uid
                ):
                    seen_sids.add(sid)
                    rows.append(doc)
                elif owner is None and sid in ids:
                    await link_session_to_user(db, session_id=sid, user_id=uid)
                    seen_sids.add(sid)
                    rows.append(doc)

    seen: set[str] = set()
    out: list[ConversationSummary] = []
    for doc in rows:
        sid = str(doc.get("session_id") or "")
        if not sid or sid in seen:
            continue
        seen.add(sid)
        updated = doc.get("updated_at") or doc.get("created_at")
        updated_iso = (
            updated.replace(tzinfo=UTC).isoformat()
            if isinstance(updated, datetime)
            else str(updated)
        )
        raw_summary = doc.get("summary")
        summary = str(raw_summary).strip() if raw_summary else None
        summary_updated = doc.get("summary_updated_at")
        summary_updated_iso = (
            summary_updated.replace(tzinfo=UTC).isoformat()
            if isinstance(summary_updated, datetime)
            else (str(summary_updated) if summary_updated else None)
        )
        out.append(
            ConversationSummary(
                session_id=sid,
                title=str(doc.get("title") or "Chat"),
                updated_at=updated_iso,
                chat_mode=CHAT_MODE,
                summary=summary or None,
                summary_updated_at=summary_updated_iso,
            )
        )
    return out


@router.delete("/conversations/{session_id}")
async def delete_conversation(session_id: str, request: Request) -> dict[str, str]:
    from app.auth.repository import delete_session_link, is_session_owned_by_user
    from app.cache.session_memory import purge_chat_session_cache
    from app.db.repository import delete_conversation_by_session, get_conversation_by_session

    db = get_db(request)
    redis = get_redis(request)
    conv = await get_conversation_by_session(db, session_id)

    if conv:
        owner = conv.get("user_id")
        if isinstance(owner, ObjectId):
            maybe_user = await resolve_optional_current_user(request, db)
            if not maybe_user:
                raise HTTPException(401, "Authentication required to delete this chat")
            uid = maybe_user.get("_id")
            if not isinstance(uid, ObjectId):
                raise HTTPException(401, "Invalid user")
            if owner != uid and not await is_session_owned_by_user(
                db, session_id=session_id, user_id=uid
            ):
                raise HTTPException(403, "You cannot delete this chat session")

        await delete_conversation_by_session(db, session_id)
        await delete_session_link(db, session_id=session_id)
        await purge_chat_session_cache(redis, session_id)

    return {"status": "deleted"}


class ActivityVideoSourceOut(BaseModel):
    name: str
    url: str | None = None
    license: str | None = None
    attribution: str | None = None


class ActivityCatalogOut(BaseModel):
    id: str
    title: str
    description: str
    content_type: str
    activity_type: str
    ui_component: str
    video_url: str | None = None
    youtube_id: str | None = None
    video_source: ActivityVideoSourceOut | None = None
    duration_min: int
    avg_rating: float
    rating_count: int
    benefits: list[str] = Field(default_factory=list)
    tags: list[str] = Field(default_factory=list)


class ActivityRateBody(BaseModel):
    session_id: str = Field(..., min_length=8, max_length=128)
    activity_id: str = Field(..., min_length=2, max_length=64)
    completion_id: str = Field(..., min_length=1)
    rating: int = Field(..., ge=1, le=5)
    message_id: str | None = Field(None, max_length=32)


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
    rows = await list_messages_for_user(db, conversation_id=cid, limit=limit)
    out: list[MessageOut] = []
    for doc in rows:
        created = doc["created_at"]
        created_iso = (
            created.replace(tzinfo=UTC).isoformat()
            if isinstance(created, datetime)
            else str(created)
        )
        meta = doc.get("metadata")
        if isinstance(meta, dict):
            meta = {**meta, "chat_mode": CHAT_MODE}
            if doc.get("role") == "assistant" and "sender_name" not in meta:
                meta["sender_name"] = "Helios"
        else:
            meta = {"chat_mode": CHAT_MODE}
            if str(doc.get("role")) == "assistant":
                meta["sender_name"] = "Helios"
        out.append(
            MessageOut(
                id=str(doc["_id"]),
                role=str(doc["role"]),
                content=str(doc["content"]),
                created_at=created_iso,
                metadata=meta,
            )
        )
    return out


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


@router.get("/activities/catalog", response_model=list[ActivityCatalogOut])
async def get_activity_catalog(
    request: Request,
    scope: str = "helios",
    lang: str = "vi",
) -> list[ActivityCatalogOut]:
    from app.db.repository import activity_to_api, list_wellness_activities
    from app.wellness.catalog_seed import DEFAULT_WELLNESS_ACTIVITIES

    db = get_db(request)
    ui_lang = lang if lang in ("vi", "en") else "vi"
    rows = await list_wellness_activities(
        db, scope=scope, active_only=True, implemented_only=True
    )
    if not rows:
        rows = [
            d
            for d in DEFAULT_WELLNESS_ACTIVITIES
            if (not scope or scope in (d.get("scope") or []))
            and d.get("active")
            and d.get("implemented")
        ]
    return [ActivityCatalogOut(**activity_to_api(r, lang=ui_lang)) for r in rows]


@router.post("/activities/rate")
async def rate_activity(body: ActivityRateBody, request: Request) -> dict[str, str]:
    from app.auth.dependencies import resolve_optional_current_user
    from app.db.repository import (
        get_activity_completion_by_id,
        save_activity_rating,
        update_message_metadata,
    )

    db = get_db(request)
    try:
        completion_oid = ObjectId(body.completion_id)
    except Exception as exc:  # noqa: BLE001
        raise HTTPException(400, "Invalid completion_id") from exc

    completion = await get_activity_completion_by_id(db, completion_oid)
    if not completion:
        raise HTTPException(404, "Completion not found")
    if completion.get("session_id") != body.session_id:
        raise HTTPException(403, "Session mismatch")
    if str(completion.get("activity_id")) != body.activity_id:
        raise HTTPException(400, "Activity mismatch")

    maybe_user = await resolve_optional_current_user(request, db)
    uid: ObjectId | None = None
    if maybe_user:
        raw = maybe_user.get("_id")
        if isinstance(raw, ObjectId):
            uid = raw

    await save_activity_rating(
        db,
        session_id=body.session_id,
        activity_id=body.activity_id,
        completion_id=completion_oid,
        rating=body.rating,
        chat_mode=CHAT_MODE,
        user_id=uid,
    )
    thanks = "Cảm ơn bạn đã đánh giá! Phản hồi của bạn giúp Helios gợi ý bài tập phù hợp hơn."
    if body.message_id:
        try:
            message_oid = ObjectId(body.message_id)
            pending = {
                "activity_id": body.activity_id,
                "completion_id": body.completion_id,
                "rated": True,
                "rating": body.rating,
            }
            await update_message_metadata(
                db,
                message_oid,
                {
                    "pending_activity_rating": pending,
                    "rating_thanks": thanks,
                    "chat_mode": CHAT_MODE,
                },
            )
        except Exception:  # noqa: BLE001
            pass
    return {"status": "ok", "message": thanks}


@router.post("/activities/complete", response_model=ActivityCompletionOut)
async def complete_activity(body: ActivityCompleteBody, request: Request) -> ActivityCompletionOut:
    from app.db.repository import is_valid_activity_id

    db = get_db(request)
    if not await is_valid_activity_id(db, body.activity_id):
        raise HTTPException(400, f"Unknown activity: {body.activity_id}")
    conv = await get_conversation_by_session(db, body.session_id)
    if not conv:
        conv = await create_conversation(db, session_id=body.session_id, chat_mode=CHAT_MODE)
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
        chat_mode=CHAT_MODE,
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


class SpeechToTextResponse(BaseModel):
    text: str
    language_code: str | None = None


@router.post("/speech/transcribe", response_model=SpeechToTextResponse)
async def transcribe_speech(
    request: Request,
    audio: UploadFile = File(...),
    language_code: str | None = Form(None),
) -> SpeechToTextResponse:
    from app.config import get_settings
    from app.speech.elevenlabs_stt import SpeechToTextError, transcribe_with_elevenlabs

    settings = get_settings()
    api_key = settings.eleven_labs_api_key
    if not api_key:
        raise HTTPException(
            503,
            detail="Speech-to-text is not configured (missing ELEVEN_LABS_API_KEY)",
        )

    raw = await audio.read()
    if not raw:
        raise HTTPException(400, detail="Empty audio file")

    filename = audio.filename or "recording.webm"
    content_type = audio.content_type or "audio/webm"

    try:
        result = await transcribe_with_elevenlabs(
            audio_bytes=raw,
            filename=filename,
            content_type=content_type,
            api_key=api_key,
            model_id=settings.eleven_labs_stt_model,
            language_code=language_code.strip() if language_code else None,
        )
    except SpeechToTextError as exc:
        raise HTTPException(400, detail=str(exc)) from exc

    return SpeechToTextResponse(
        text=str(result["text"]),
        language_code=result.get("language_code"),
    )
