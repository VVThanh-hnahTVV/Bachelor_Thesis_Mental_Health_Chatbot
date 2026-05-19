from __future__ import annotations

import asyncio
from datetime import UTC, datetime, timedelta
from typing import Any

from bson import ObjectId
from fastapi import APIRouter, HTTPException, Request
from pydantic import BaseModel, Field

from app.auth.dependencies import resolve_optional_current_user
from app.auth.repository import link_session_to_user
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
    crisis_reply_for_language,
    run_safety_engine,
)
from app.graph.conversation_ui import (
    is_learn_exploration,
    should_skip_quick_replies,
    should_skip_wellness_suggestions,
)
from app.graph.dynamic_quick_replies import generate_follow_up_quick_replies
from app.graph.guided_quick_replies import ensure_three_quick_replies
from app.graph.nodes.response_generator import detect_language, is_meta_conversation
from app.graph.workflow import run_turn
from app.wellness.activity_profile import load_activity_profile
from app.wellness.conversation_state import ConvState, advance_conv_state
from app.wellness.recommendation_engine import (
    RecommendationSignals,
    SuggestionIntensity,
    depression_level as _depression_level,
    implicit_phq2_scores,
    should_show_activity_micro_feedback,
)
from app.wellness.session import (
    get_last_suggestion_turn,
    get_session as get_wellness_session,
    is_wellness_active,
    mark_suggestion_turn,
)
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


class QuickReplyOut(BaseModel):
    id: str
    label: str
    message: str


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
    quick_replies: list[QuickReplyOut] = Field(default_factory=list)
    metadata: dict[str, Any] | None = None


class MessageFeedbackRequest(BaseModel):
    session_id: str = Field(..., min_length=8, max_length=128)
    assistant_message_id: str = Field(..., min_length=1)
    value: str = Field(..., pattern="^(yes|a_bit|no)$")


class WellnessStartRequest(BaseModel):
    session_id: str = Field(..., min_length=8, max_length=128)
    activity_id: str = Field(..., pattern="^(breathing_box|ocean_sound)$")


class WellnessCompleteRequest(BaseModel):
    session_id: str = Field(..., min_length=8, max_length=128)


class ScreeningSubmitRequest(BaseModel):
    session_id: str = Field(..., min_length=8, max_length=128)
    instrument: str = Field(..., pattern="^(phq2|phq4)$")
    answers: list[int] = Field(..., min_length=2, max_length=4)


class ScreeningOut(BaseModel):
    instrument: str
    score: int
    interpretation: str
    disclaimer: str
    created_at: str


# ---------------------------------------------------------------------------
# Chat endpoint
# ---------------------------------------------------------------------------

@router.post("/chat", response_model=ChatResponse)
async def chat(req: ChatRequest, request: Request) -> ChatResponse:
    from app.cache.session_memory import (
        get_personalization_context,
        get_turns,
        push_turn,
        set_personalization_context,
    )
    from app.db.repository import count_user_messages
    from app.graph.nodes.memory_update import run_memory_update
    from app.personalization.context import build_personalization_context

    db = get_db(request)
    redis = get_redis(request)
    maybe_user = await resolve_optional_current_user(request, db)
    if maybe_user:
        uid = maybe_user.get("_id")
        if isinstance(uid, ObjectId):
            # Keep chat flow backward compatible while linking authenticated users
            # so personalization context can access user profile/name immediately.
            await link_session_to_user(db, session_id=req.session_id, user_id=uid)

    personalization_context: dict[str, Any] = {}
    if redis is not None:
        cached_ctx = await get_personalization_context(redis, req.session_id)
        if isinstance(cached_ctx, dict):
            personalization_context = cached_ctx
    if not personalization_context:
        personalization_context = await build_personalization_context(
            db,
            session_id=req.session_id,
            include_user_display=True,
        )
        if redis is not None:
            await set_personalization_context(
                redis,
                req.session_id,
                personalization_context,
            )

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

    from app.cache.therapy_flags import (
        get_therapy_flags,
        update_therapy_flags_after_turn,
    )

    therapy_flags = await get_therapy_flags(redis, req.session_id)

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
        "personalization_context": personalization_context,
        "therapy_flags": therapy_flags,
    }

    safety_task = asyncio.create_task(
        run_safety_engine(req.message, history, provider)
    )
    main_task = asyncio.create_task(run_turn(graph_state))

    safety_result, graph_out = await asyncio.gather(safety_task, main_task)

    # -----------------------------------------------------------------------
    # Merge: safety overrides if emergency
    # -----------------------------------------------------------------------
    conv_state: ConvState = ConvState.CRISIS if safety_result.get("emergency_mode") else ConvState.OPENING
    suggestion_intensity: SuggestionIntensity = SuggestionIntensity.MEDIUM

    if safety_result["emergency_mode"]:
        _crisis_lang = detect_language(req.message, history)
        reply, crisis_choices = crisis_reply_for_language(_crisis_lang)
        chat_blocked = True
        message_type = "crisis"
        suggested_activities: list[dict[str, Any]] = []
        emotion = graph_out.get("primary_emotion")
        therapy_strategy = None
        meta_out: dict[str, Any] = {
            "risk_level": safety_result["risk_level"],
            "safety_confidence": safety_result["confidence"],
            "safety_triggers": safety_result["triggers"],
            "safety_fallback_used": "llm_failure" in safety_result["triggers"],
            "conv_state": ConvState.CRISIS.value,
            "suggestion_intensity": SuggestionIntensity.MEDIUM.value,
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
        _objection = bool(graph_out.get("objection_detected"))
        _lang = detect_language(req.message, history)
        wellness_state = await get_wellness_session(redis, req.session_id)
        _skip_wellness = (
            message_type != "normal"
            or _intent == "casual"
            or _strategy == "stabilization"
            or is_meta_conversation(req.message)
            or _objection
            or is_wellness_active(wellness_state)
            or should_skip_wellness_suggestions(
                user_input=req.message,
                intent=_intent,
                therapy_strategy=therapy_strategy,
                reply=reply,
            )
        )

        user_turn_count = await count_user_messages(db, cid) + 1
        _risk = str(safety_result.get("risk_level") or "low")
        _emotion_intensity = float(graph_out.get("emotion_intensity") or 0.5)

        # Parallel: load suggestion cooldown + activity profile
        last_suggest_turn, activity_profile = await asyncio.gather(
            get_last_suggestion_turn(redis, req.session_id),
            load_activity_profile(db, req.session_id),
        )
        turns_since_suggest: int | None = None
        if last_suggest_turn is not None:
            turns_since_suggest = user_turn_count - last_suggest_turn

        # Advance conversation state machine
        conv_state: ConvState = await advance_conv_state(
            redis,
            session_id=req.session_id,
            intent=_intent,
            primary_emotion=str(emotion or "neutral"),
            emotion_intensity=_emotion_intensity,
            therapy_strategy=therapy_strategy,
            risk_level=_risk,
            user_turn_count=user_turn_count,
            therapy_flags=therapy_flags,
        )

        await update_therapy_flags_after_turn(
            redis,
            session_id=req.session_id,
            therapy_strategy=therapy_strategy,
            user_turn_count=user_turn_count,
        )

        recent_user_blob = "\n".join(
            m.get("content", "") for m in history if m.get("role") == "user"
        )
        if recent_user_blob:
            recent_user_blob = f"{recent_user_blob}\n{req.message}"
        else:
            recent_user_blob = req.message

        wellness_signals = RecommendationSignals(
            user_input=req.message,
            assistant_reply=reply,
            intent=_intent,
            primary_emotion=str(emotion or "neutral"),
            emotion_intensity=_emotion_intensity,
            therapy_strategy=therapy_strategy,
            user_turn_count=user_turn_count,
            risk_level=_risk,
            history=history,
            turns_since_last_suggestion=turns_since_suggest,
            objection_detected=_objection,
            conv_state=conv_state,
            activity_profile=activity_profile,
        )

        suggestion_intensity = SuggestionIntensity.MEDIUM
        if not _skip_wellness:
            suggested_activities, suggestion_intensity = await detect_suggested_activities_llm(
                user_input=req.message,
                assistant_reply=reply,
                risk_level=_risk,
                provider=provider,
                recent_user_messages=recent_user_blob,
                signals=wellness_signals,
            )
            if suggested_activities:
                await mark_suggestion_turn(redis, req.session_id, user_turn_count)
            reply = align_assistant_reply_with_suggestions(
                reply,
                suggested_activities,
                suggestion_intensity,
                therapy_strategy=therapy_strategy,
            )
        else:
            suggested_activities = []

        quick_replies: list[dict[str, str]] = []
        if not should_skip_quick_replies(
            user_input=req.message,
            intent=_intent,
            therapy_strategy=therapy_strategy,
            objection_detected=_objection,
            chat_blocked=chat_blocked,
            message_type=message_type,
            suggested_activities=suggested_activities,
        ):
            quick_replies = await generate_follow_up_quick_replies(
                user_input=req.message,
                assistant_reply=reply,
                lang=_lang,
                provider=provider,
                intent=_intent,
                emotion=emotion,
                therapy_strategy=therapy_strategy,
            )
            quick_replies = ensure_three_quick_replies(
                quick_replies,
                lang=_lang,
                strategy=therapy_strategy,
                emotion=str(emotion or "neutral"),
                intent=_intent,
            )

        from app.db.repository import recent_messages as _recent_messages
        _rich_history = await _recent_messages(db, cid, limit=20)
        _phq_q1, _phq_q2 = implicit_phq2_scores(_rich_history)
        _dep_level = _depression_level(_phq_q1, _phq_q2)

        # When implicit depression signal is moderate/high and current strategy
        # is only passive listening, nudge toward behavioral_activation so Luna
        # gently encourages small positive actions within the conversation.
        if (
            _dep_level in ("moderate", "high")
            and therapy_strategy == "reflective_listening"
            and _intent not in ("casual",)
            and not chat_blocked
        ):
            therapy_strategy = "behavioral_activation"

        show_feedback = (
            message_type == "normal"
            and not chat_blocked
            and should_show_activity_micro_feedback(
                user_turn_count=user_turn_count,
                intent=_intent,
                therapy_strategy=therapy_strategy,
                reply=reply,
                suggested_activities=suggested_activities,
                objection_detected=_objection,
                conv_state=conv_state,
            )
        )

        meta_out = {
            "risk_level": safety_result["risk_level"],
            "safety_confidence": safety_result["confidence"],
            "safety_fallback_used": "llm_failure" in safety_result["triggers"],
            "emotion": emotion,
            "emotion_intensity": _emotion_intensity,
            "intent": _intent,
            "therapy_strategy": therapy_strategy,
            "objection_detected": _objection,
            "conv_state": conv_state.value,
            "suggestion_intensity": suggestion_intensity.value,
            "suggested_activities": suggested_activities,
            "quick_replies": quick_replies,
            "show_micro_feedback": show_feedback,
            "implicit_phq2": {"q1": _phq_q1, "q2": _phq_q2, "level": _dep_level},
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
        async def _update_profile_and_cache() -> None:
            await run_memory_update(db, req.session_id, req.message, reply, provider)
            if redis is not None:
                refreshed = await build_personalization_context(
                    db,
                    session_id=req.session_id,
                    include_user_display=True,
                )
                await set_personalization_context(redis, req.session_id, refreshed)

        asyncio.create_task(_update_profile_and_cache())

    qr_out: list[QuickReplyOut] = []
    if not chat_blocked:
        qr_out = [QuickReplyOut(**q) for q in (meta_out.get("quick_replies") or [])]

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
        quick_replies=qr_out,
        metadata=meta_out,
    )


@router.post("/chat/feedback")
async def submit_message_feedback(body: MessageFeedbackRequest, request: Request) -> dict[str, str]:
    from app.db.repository import save_message_feedback

    db = get_db(request)
    await save_message_feedback(
        db,
        session_id=body.session_id,
        assistant_message_id=body.assistant_message_id,
        value=body.value,
    )
    return {"status": "ok"}


@router.post("/wellness/start", response_model=ChatResponse)
async def wellness_start(body: WellnessStartRequest, request: Request) -> ChatResponse:
    from app.cache.session_memory import push_turn
    from app.wellness.session import set_active, start_session

    db = get_db(request)
    redis = get_redis(request)
    conv = await get_conversation_by_session(db, body.session_id)
    if not conv:
        conv = await create_conversation(db, session_id=body.session_id)
    cid = conv["_id"]
    assert isinstance(cid, ObjectId)

    lang = "vi"
    _, intro = await start_session(redis, session_id=body.session_id, activity_id=body.activity_id, lang=lang)
    await set_active(redis, body.session_id)

    meta_out: dict[str, Any] = {
        "wellness_session": {"activity_id": body.activity_id, "step": "active"},
        "show_micro_feedback": False,
    }
    assistant_doc = await append_message(
        db,
        conversation_id=cid,
        role="assistant",
        content=intro,
        metadata=meta_out,
    )
    aid = assistant_doc.get("_id")
    if redis is not None:
        await push_turn(redis, body.session_id, "assistant", intro)

    return ChatResponse(
        reply=intro,
        session_id=body.session_id,
        conversation_id=str(cid),
        assistant_message_id=str(aid) if aid else None,
        provider=default_provider(),
        suggested_activities=[
            ActivitySuggestionOut(
                id=body.activity_id,
                title="Bài tập" if body.activity_id == "breathing_box" else "Âm sóng",
                description="",
            )
        ],
        metadata=meta_out,
    )


@router.post("/wellness/complete")
async def wellness_complete(body: WellnessCompleteRequest, request: Request) -> dict[str, Any]:
    from app.wellness.session import clear_session, complete_session

    redis = get_redis(request)
    state, checkin_msg = await complete_session(redis, session_id=body.session_id, lang="vi")
    await clear_session(redis, body.session_id)
    return {
        "checkin_message": checkin_msg,
        "show_micro_feedback": True,
        "wellness_session": state,
    }


@router.post("/screening", response_model=ScreeningOut)
async def submit_screening(body: ScreeningSubmitRequest, request: Request) -> ScreeningOut:
    from app.db.repository import save_screening_response
    from app.screening.phq import DISCLAIMER_VI, get_questions, interpret_phq2, score_phq

    expected = 2 if body.instrument == "phq2" else 4
    if len(body.answers) != expected:
        raise HTTPException(400, f"Expected {expected} answers for {body.instrument}")
    if any(a < 0 or a > 3 for a in body.answers):
        raise HTTPException(400, "Each answer must be 0-3")

    score = score_phq(body.answers)
    db = get_db(request)
    doc = await save_screening_response(
        db,
        session_id=body.session_id,
        instrument=body.instrument,
        answers=body.answers,
        score=score,
    )
    created = doc["created_at"]
    created_iso = (
        created.replace(tzinfo=UTC).isoformat()
        if isinstance(created, datetime)
        else str(created)
    )
    return ScreeningOut(
        instrument=body.instrument,
        score=score,
        interpretation=interpret_phq2(score),
        disclaimer=DISCLAIMER_VI,
        created_at=created_iso,
    )


@router.get("/screening/latest", response_model=ScreeningOut | None)
async def get_latest_screening(
    session_id: str,
    request: Request,
    instrument: str | None = None,
) -> ScreeningOut | None:
    from app.db.repository import latest_screening
    from app.screening.phq import DISCLAIMER_VI, interpret_phq2

    db = get_db(request)
    doc = await latest_screening(db, session_id=session_id, instrument=instrument)
    if not doc:
        return None
    created = doc["created_at"]
    created_iso = (
        created.replace(tzinfo=UTC).isoformat()
        if isinstance(created, datetime)
        else str(created)
    )
    score = int(doc["score"])
    return ScreeningOut(
        instrument=str(doc["instrument"]),
        score=score,
        interpretation=interpret_phq2(score),
        disclaimer=DISCLAIMER_VI,
        created_at=created_iso,
    )


@router.get("/screening/questions")
async def screening_questions(instrument: str = "phq2") -> dict[str, Any]:
    from app.screening.phq import DISCLAIMER_VI, OPTIONS_VI, get_questions

    if instrument not in ("phq2", "phq4"):
        raise HTTPException(400, "instrument must be phq2 or phq4")
    return {
        "instrument": instrument,
        "questions": get_questions(instrument),
        "options": OPTIONS_VI,
        "disclaimer": DISCLAIMER_VI,
    }


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
# Dashboard stats (chat emotions + wellness activity)
# ---------------------------------------------------------------------------

class DashboardStatsOut(BaseModel):
    mood_score: int | None = None
    mood_source: str = "none"  # "chat" | "form" | "none"
    dominant_emotion: str | None = None
    emotion_samples_today: int = 0
    completion_rate: int = 0
    therapy_sessions: int = 0
    total_activities_today: int = 0
    chat_turns_today: int = 0
    last_updated: str


@router.get("/dashboard/stats", response_model=DashboardStatsOut)
async def dashboard_stats(session_id: str, request: Request) -> DashboardStatsOut:
    from app.db.repository import list_activity_completions, list_conversations, list_mood_entries
    from app.wellness.emotion_scores import aggregate_chat_emotions_today

    db = get_db(request)
    now = datetime.now(UTC)
    day_start = now.replace(hour=0, minute=0, second=0, microsecond=0)

    message_docs: list[dict[str, Any]] = []
    conv = await get_conversation_by_session(db, session_id)
    if conv:
        cid = conv["_id"]
        assert isinstance(cid, ObjectId)
        message_docs = await list_messages_chronological(db, conversation_id=cid, limit=500)

    chat_agg = aggregate_chat_emotions_today(message_docs, day_start=day_start)

    day_end = day_start + timedelta(days=1)
    mood_rows = await list_mood_entries(db, session_id=session_id, limit=60)
    today_form_scores = []
    for row in mood_rows:
        created = row.get("created_at")
        if not isinstance(created, datetime):
            continue
        created_dt = created if created.tzinfo else created.replace(tzinfo=UTC)
        if not (day_start <= created_dt < day_end):
            continue
        score = row.get("score")
        if score is not None:
            today_form_scores.append(int(score) * 10)

    if chat_agg["mood_score"] is not None:
        mood_score = int(chat_agg["mood_score"])
        mood_source = "chat"
        dominant_emotion = chat_agg.get("dominant_emotion")
        emotion_samples = int(chat_agg.get("samples") or 0)
    elif today_form_scores:
        mood_score = round(sum(today_form_scores) / len(today_form_scores))
        mood_source = "form"
        dominant_emotion = None
        emotion_samples = 0
    else:
        mood_score = None
        mood_source = "none"
        dominant_emotion = None
        emotion_samples = 0

    activity_rows = await list_activity_completions(db, session_id=session_id, limit=200)
    activities_today = 0
    for doc in activity_rows:
        created = doc.get("created_at")
        if not isinstance(created, datetime):
            continue
        created_dt = created if created.tzinfo else created.replace(tzinfo=UTC)
        if day_start <= created_dt < day_end:
            activities_today += 1

    chat_turns_today = 0
    for doc in message_docs:
        if doc.get("role") != "user":
            continue
        created = doc.get("created_at")
        if not isinstance(created, datetime):
            continue
        created_dt = created if created.tzinfo else created.replace(tzinfo=UTC)
        if day_start <= created_dt < day_end:
            chat_turns_today += 1

    sessions = await list_conversations(db, session_id=session_id, limit=100)
    total_today = activities_today + len(today_form_scores)
    engaged = bool(emotion_samples or today_form_scores or activities_today or chat_turns_today)

    return DashboardStatsOut(
        mood_score=mood_score,
        mood_source=mood_source,
        dominant_emotion=dominant_emotion,
        emotion_samples_today=emotion_samples,
        completion_rate=100 if engaged else 0,
        therapy_sessions=len(sessions),
        total_activities_today=total_today,
        chat_turns_today=chat_turns_today,
        last_updated=now.isoformat(),
    )


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
