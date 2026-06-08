from __future__ import annotations

import asyncio
import json
from datetime import UTC, datetime, timedelta
from typing import Any, Literal

from bson import ObjectId
from fastapi import APIRouter, File, Form, HTTPException, Request, UploadFile
from fastapi.responses import StreamingResponse
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
from app.graph.crisis_escalation import (
    CrisisStage,
    advance_crisis_escalation,
    chips_for_stage,
    confirm_reply_for_language,
    crisis_choices_to_api,
    get_crisis_escalation,
    human_escalation_reply_for_language,
    overwhelm_reply_for_language,
    overwhelm_doing_reply_for_language,
    overwhelm_check_reply_for_language,
    overwhelm_not_better_reply_for_language,
    safety_watch_reply_for_language,
    someone_else_reply_for_language,
    recovery_reply_for_language,
    parse_crisis_chip_id,
    pre_gather_force_strategy,
    safety_result_for_chip,
    should_block_free_text,
    sos_reply_and_chips,
    strategy_for_chip,
    user_message_for_storage,
)
from app.graph.safety_engine import run_safety_engine
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
    chat_mode: str = "psychologist"


class ChatRequest(BaseModel):
    message: str = Field(..., min_length=1, max_length=8000)
    session_id: str = Field(..., min_length=8, max_length=128)
    provider: str | None = None
    chat_mode: Literal["psychologist", "medical"] | None = None


class ActivitySuggestionOut(BaseModel):
    id: str
    title: str
    description: str


class QuickReplyOut(BaseModel):
    id: str
    label: str
    message: str


class CrisisChoiceOut(BaseModel):
    id: str
    label: str


class ChatResponse(BaseModel):
    reply: str
    session_id: str
    conversation_id: str
    assistant_message_id: str | None = None
    provider: str
    # Safety / routing
    chat_blocked: bool = False
    crisis_choices: list[CrisisChoiceOut] = Field(default_factory=list)
    crisis_stage: str = "none"
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
    quiet: bool = False
    lang: str | None = Field(None, pattern="^(vi|en)$")


class WellnessCompleteRequest(BaseModel):
    session_id: str = Field(..., min_length=8, max_length=128)
    lang: str | None = Field(None, pattern="^(vi|en)$")


class ScreeningSubmitRequest(BaseModel):
    session_id: str = Field(..., min_length=8, max_length=128)
    instrument: str = Field(..., pattern="^(phq2|phq4)$")
    answers: list[int] = Field(..., min_length=2, max_length=4)
    lang: str | None = Field(None, pattern="^(vi|en)$")


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
    return await _execute_chat(req, request)


async def _execute_chat(req: ChatRequest, request: Request) -> ChatResponse:
    from app.chat_progress import emit_progress
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
    uid: ObjectId | None = None
    if maybe_user:
        raw_uid = maybe_user.get("_id")
        if isinstance(raw_uid, ObjectId):
            uid = raw_uid

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

    from app.api.medical_handlers import (
        handle_medical_chat_turn,
        resolve_conversation_mode,
    )

    conv = await get_conversation_by_session(db, req.session_id)
    conv, chat_mode = await resolve_conversation_mode(
        db,
        session_id=req.session_id,
        requested_mode=req.chat_mode,
        conv=conv,
        user_id=uid,
    )
    if uid is not None:
        await link_session_to_user(db, session_id=req.session_id, user_id=uid)
    cid = conv["_id"]
    assert isinstance(cid, ObjectId)

    if redis is not None:
        history = await get_turns(redis, req.session_id, limit=20)
    else:
        history = []

    _crisis_lang_early = detect_language(req.message, history)
    user_message_stored = user_message_for_storage(req.message, _crisis_lang_early)

    # Persist user message to MongoDB (display-friendly text for chip taps)
    await append_message(
        db,
        conversation_id=cid,
        role="user",
        content=user_message_stored,
        metadata={"chat_mode": chat_mode},
    )

    user_turn_count_after = await count_user_messages(db, cid)
    default_titles = {"New chat", "Chat", ""}
    current_title = str(conv.get("title") or "")
    if user_turn_count_after == 1 and current_title in default_titles:
        from app.db.repository import update_conversation_title
        from app.graph.conversation_title import generate_conversation_title

        title = await generate_conversation_title(
            req.message,
            provider=default_provider(),
        )
        await update_conversation_title(db, cid, title)
        conv["title"] = title

    if chat_mode == "medical":
        emit_progress("analyzing_request")
        medical_provider = default_provider()
        from app.conversation.context import load_conversation_summary

        conversation_summary = await load_conversation_summary(db, redis, req.session_id)
        reply, meta, assistant_message_id = await handle_medical_chat_turn(
            db,
            session_id=req.session_id,
            conversation_id=cid,
            message=req.message,
            conversation_summary=conversation_summary,
        )
        from app.conversation.summary import schedule_conversation_summary_update

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
            chat_blocked=False,
            crisis_choices=[],
            crisis_stage="none",
            message_type="medical",
            metadata=meta,
        )

    # Short-term history from Redis (fast); push user turn
    if redis is not None:
        await push_turn(redis, req.session_id, "user", user_message_stored)
        history = await get_turns(redis, req.session_id, limit=20)
        # Exclude the turn we just pushed (the last one) so history = prior context
        history = history[:-1]
    else:
        history = []

    default_p: ProviderName = default_provider()
    provider: ProviderName = resolve_provider(req.provider, default=default_p)

    from app.cache.therapy_flags import (
        get_therapy_flags,
        update_therapy_flags_after_turn,
    )

    therapy_flags = await get_therapy_flags(redis, req.session_id)
    escalation_pre = await get_crisis_escalation(redis, req.session_id)
    crisis_chip_id = parse_crisis_chip_id(req.message)
    force_strategy = pre_gather_force_strategy(escalation_pre, req.message)

    # -----------------------------------------------------------------------
    # Parallel: safety engine + main LangGraph graph
    # -----------------------------------------------------------------------
    graph_state: dict[str, Any] = {
        "user_input": req.message,
        "history": history,
        "provider": provider,
        "session_id": req.session_id,
        "db": db,
        "personalization_context": personalization_context,
        "therapy_flags": therapy_flags,
        "force_therapy_strategy": force_strategy,
        "crisis_chip_id": crisis_chip_id,
    }

    emit_progress("analyzing_request")
    emit_progress("safety_check")
    safety_task = asyncio.create_task(
        run_safety_engine(req.message, history, provider)
    )
    main_task = asyncio.create_task(run_turn(graph_state))

    safety_result, graph_out = await asyncio.gather(safety_task, main_task)
    chip_safety = safety_result_for_chip(crisis_chip_id)
    if chip_safety is not None:
        safety_result = chip_safety

    _crisis_lang = detect_language(req.message, history)
    crisis_stage, _escalation_state = await advance_crisis_escalation(
        redis,
        req.session_id,
        safety=safety_result,
        user_message=req.message,
    )

    # -----------------------------------------------------------------------
    # Merge: Wysa-style gradual crisis (concern → confirm → sos)
    # -----------------------------------------------------------------------
    conv_state: ConvState = (
        ConvState.CRISIS if crisis_stage == CrisisStage.SOS else ConvState.OPENING
    )
    suggestion_intensity: SuggestionIntensity = SuggestionIntensity.MEDIUM
    crisis_choices_out: list[CrisisChoiceOut] = []

    if crisis_stage != CrisisStage.NONE:
        chat_blocked = should_block_free_text(crisis_stage)
        message_type = "normal"
        suggested_activities: list[dict[str, Any]] = []
        emotion = graph_out.get("primary_emotion")
        crisis_chips = chips_for_stage(crisis_stage, _crisis_lang)
        crisis_choices_out = [
            CrisisChoiceOut(**c) for c in crisis_choices_to_api(crisis_chips)
        ]

        if crisis_stage == CrisisStage.SOS:
            reply, _sos_chips = sos_reply_and_chips(_crisis_lang)
            therapy_strategy = None
            conv_state = ConvState.CRISIS
        elif crisis_stage == CrisisStage.CONFIRM:
            reply = confirm_reply_for_language(_crisis_lang)
            therapy_strategy = "crisis_concern"
        elif crisis_stage == CrisisStage.HUMAN_ESCALATION:
            reply = human_escalation_reply_for_language(_crisis_lang, crisis_chip_id)
            therapy_strategy = "crisis_safety_check"
            conv_state = ConvState.CRISIS
        elif crisis_stage == CrisisStage.OVERWHELM:
            reply = overwhelm_reply_for_language(_crisis_lang)
            therapy_strategy = "crisis_grounding"
        elif crisis_stage == CrisisStage.OVERWHELM_DOING:
            reply = overwhelm_doing_reply_for_language(_crisis_lang, crisis_chip_id)
            message_type = "wellness_activity"
            therapy_strategy = "crisis_grounding"
        elif crisis_stage == CrisisStage.OVERWHELM_CHECK:
            reply = overwhelm_check_reply_for_language(_crisis_lang)
            therapy_strategy = "crisis_grounding"
        elif crisis_stage == CrisisStage.OVERWHELM_NOT_BETTER:
            reply = overwhelm_not_better_reply_for_language(_crisis_lang)
            therapy_strategy = "crisis_safety_check"
        elif crisis_stage == CrisisStage.SAFETY_WATCH:
            reply = safety_watch_reply_for_language(_crisis_lang)
            therapy_strategy = "crisis_reassure"
        elif crisis_stage in (CrisisStage.SOMEONE_ELSE, CrisisStage.SOMEONE_ELSE_FOLLOWUP):
            reply = someone_else_reply_for_language(_crisis_lang, crisis_chip_id)
            therapy_strategy = "crisis_resources"
        elif crisis_stage == CrisisStage.RECOVERY:
            reply = recovery_reply_for_language(_crisis_lang)
            therapy_strategy = "crisis_reassure"
        else:
            reply = str(graph_out.get("final_reply") or "").strip()
            if not reply:
                reply = (
                    "I'm here with you. You are not alone right now."
                    if _crisis_lang == "en"
                    else "Mình ở đây với bạn. Bạn không đơn độc trong lúc này."
                )
            therapy_strategy = (
                strategy_for_chip(crisis_chip_id)
                or str(graph_out.get("therapy_strategy") or "crisis_concern")
            )

        meta_out = {
            "risk_level": safety_result["risk_level"],
            "safety_confidence": safety_result["confidence"],
            "safety_triggers": safety_result["triggers"],
            "safety_fallback_used": "llm_failure" in safety_result["triggers"],
            "crisis_stage": crisis_stage.value,
            "crisis_chip_id": crisis_chip_id,
            "conv_state": conv_state.value,
            "suggestion_intensity": SuggestionIntensity.MEDIUM.value,
            "emotion": emotion,
            "therapy_strategy": therapy_strategy,
        }
    else:
        reply = str(graph_out.get("final_reply") or "").strip()
        if not reply:
            reply = "Mình ở đây với bạn. Bạn có thể chia sẻ thêm không?"
        chat_blocked = False
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
            crisis_stage="none",
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
                reply_language=_lang,
                user_input=req.message,
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
                user_input=req.message,
                primary_emotion=str(emotion or "neutral"),
                emotion_intensity=_emotion_intensity,
            )
        )

        meta_out = {
            "risk_level": safety_result["risk_level"],
            "safety_confidence": safety_result["confidence"],
            "safety_fallback_used": "llm_failure" in safety_result["triggers"],
            "crisis_stage": "none",
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
            "crisis_stage": crisis_stage.value,
            "crisis_choices": [c.model_dump() for c in crisis_choices_out],
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

    if reply.strip():
        from app.conversation.summary import schedule_conversation_summary_update

        schedule_conversation_summary_update(
            db,
            redis,
            session_id=req.session_id,
            conversation_id=cid,
            user_message=user_message_stored,
            assistant_reply=reply,
            provider=provider,
        )

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
        crisis_choices=crisis_choices_out,
        crisis_stage=crisis_stage.value,
        message_type=message_type,
        emotion=emotion,
        therapy_strategy=therapy_strategy,
        suggested_activities=[ActivitySuggestionOut(**s) for s in suggested_activities],
        quick_replies=qr_out,
        metadata=meta_out,
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

    lang = "en"

    async def event_generator():
        loop = asyncio.get_running_loop()
        progress_queue: asyncio.Queue[str] = asyncio.Queue()
        last_label: list[str | None] = [None]

        def _enqueue(step: str) -> None:
            label = label_for_step(step, lang)
            if label == last_label[0]:
                return
            last_label[0] = label
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
            # Padding comment so proxies/browsers flush early SSE chunks.
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
                "chat_blocked": result.chat_blocked,
                "crisis_choices": [c.model_dump() for c in result.crisis_choices],
                "crisis_stage": result.crisis_stage,
                "message_type": result.message_type,
                "emotion": result.emotion,
                "therapy_strategy": result.therapy_strategy,
                "quick_replies": [q.model_dump() for q in result.quick_replies],
                "metadata": result.metadata,
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


@router.post("/chat/upload", response_model=ChatResponse)
async def chat_upload(
    request: Request,
    session_id: str = Form(...),
    image: UploadFile = File(...),
    text: str = Form(""),
    chat_mode: str = Form("medical"),
) -> ChatResponse:
    from app.api.medical_handlers import (
        handle_medical_upload_turn,
        resolve_conversation_mode,
    )

    db = get_db(request)
    redis = get_redis(request)
    conv = await get_conversation_by_session(db, session_id)
    conv, mode = await resolve_conversation_mode(
        db,
        session_id=session_id,
        requested_mode=chat_mode,
        conv=conv,
    )
    if mode != "medical":
        raise HTTPException(400, detail="Image upload is only available in medical mode")
    cid = conv["_id"]
    assert isinstance(cid, ObjectId)

    image_bytes = await image.read()
    filename = image.filename or "upload.jpg"
    try:
        from app.storage.cloudinary import upload_chat_image

        image_url = await upload_chat_image(
            image_bytes,
            filename=filename,
            session_id=session_id,
        )
    except ValueError as exc:
        raise HTTPException(503, detail=str(exc)) from exc
    except RuntimeError as exc:
        raise HTTPException(502, detail=str(exc)) from exc

    user_content = text.strip() or "[Medical image upload]"
    await append_message(
        db,
        conversation_id=cid,
        role="user",
        content=user_content,
        metadata={
            "chat_mode": "medical",
            "has_image": True,
            "image_url": image_url,
        },
    )

    from app.conversation.context import load_conversation_summary

    conversation_summary = await load_conversation_summary(db, redis, session_id)
    reply, meta, assistant_message_id = await handle_medical_upload_turn(
        db,
        session_id=session_id,
        conversation_id=cid,
        image_bytes=image_bytes,
        filename=filename,
        text=text,
        conversation_summary=conversation_summary,
    )
    medical_provider = default_provider()
    from app.conversation.summary import schedule_conversation_summary_update

    schedule_conversation_summary_update(
        db,
        redis,
        session_id=session_id,
        conversation_id=cid,
        user_message=user_content,
        assistant_reply=reply,
        provider=medical_provider,
    )
    return ChatResponse(
        reply=reply,
        session_id=session_id,
        conversation_id=str(cid),
        assistant_message_id=assistant_message_id,
        provider=medical_provider,
        chat_blocked=False,
        crisis_choices=[],
        crisis_stage="none",
        message_type="medical",
        metadata={**(meta or {}), "image_url": image_url},
    )


@router.post("/chat/validate", response_model=ChatResponse)
async def chat_validate(
    request: Request,
    session_id: str = Form(...),
    validation_result: str = Form(...),
    comments: str | None = Form(None),
) -> ChatResponse:
    from app.api.medical_handlers import (
        handle_medical_validation_turn,
        resolve_conversation_mode,
    )

    db = get_db(request)
    redis = get_redis(request)
    conv = await get_conversation_by_session(db, session_id)
    if not conv:
        raise HTTPException(404, detail="Session not found")
    _, mode = await resolve_conversation_mode(
        db,
        session_id=session_id,
        requested_mode=None,
        conv=conv,
    )
    if mode != "medical":
        raise HTTPException(400, detail="Validation is only for medical sessions")
    cid = conv["_id"]
    assert isinstance(cid, ObjectId)

    stored = f"Validation: {validation_result}"
    if comments:
        stored += f" — {comments}"
    await append_message(
        db,
        conversation_id=cid,
        role="user",
        content=stored,
        metadata={"chat_mode": "medical", "validation_input": True},
    )

    from app.conversation.context import load_conversation_summary

    conversation_summary = await load_conversation_summary(db, redis, session_id)
    reply, meta, assistant_message_id = await handle_medical_validation_turn(
        db,
        session_id=session_id,
        conversation_id=cid,
        validation_result=validation_result,
        comments=comments,
        conversation_summary=conversation_summary,
    )
    medical_provider = default_provider()
    from app.conversation.summary import schedule_conversation_summary_update

    schedule_conversation_summary_update(
        db,
        redis,
        session_id=session_id,
        conversation_id=cid,
        user_message=stored,
        assistant_reply=reply,
        provider=medical_provider,
    )
    return ChatResponse(
        reply=reply,
        session_id=session_id,
        conversation_id=str(cid),
        assistant_message_id=assistant_message_id,
        provider=medical_provider,
        chat_blocked=False,
        crisis_choices=[],
        crisis_stage="none",
        message_type="medical",
        metadata=meta,
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

    lang = body.lang if body.lang in ("vi", "en") else "vi"
    _, intro = await start_session(redis, session_id=body.session_id, activity_id=body.activity_id, lang=lang)
    await set_active(redis, body.session_id)

    meta_out: dict[str, Any] = {
        "wellness_session": {"activity_id": body.activity_id, "step": "active"},
        "show_micro_feedback": False,
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
        if redis is not None:
            await push_turn(redis, body.session_id, "assistant", intro)

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
    from app.wellness.session import clear_session, complete_session

    redis = get_redis(request)
    lang = body.lang if body.lang in ("vi", "en") else "vi"
    state, checkin_msg = await complete_session(redis, session_id=body.session_id, lang=lang)
    await clear_session(redis, body.session_id)
    return {
        "checkin_message": checkin_msg,
        "show_micro_feedback": True,
        "wellness_session": state,
    }


@router.post("/screening", response_model=ScreeningOut)
async def submit_screening(body: ScreeningSubmitRequest, request: Request) -> ScreeningOut:
    from app.db.repository import save_screening_response
    from app.screening.phq import get_disclaimer, get_options, get_questions, interpret_phq2, score_phq

    expected = 2 if body.instrument == "phq2" else 4
    if len(body.answers) != expected:
        raise HTTPException(400, f"Expected {expected} answers for {body.instrument}")
    if any(a < 0 or a > 3 for a in body.answers):
        raise HTTPException(400, "Each answer must be 0-3")

    lang = body.lang if body.lang in ("vi", "en") else "en"
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
        interpretation=interpret_phq2(score, lang),
        disclaimer=get_disclaimer(lang),
        created_at=created_iso,
    )


@router.get("/screening/latest", response_model=ScreeningOut | None)
async def get_latest_screening(
    session_id: str,
    request: Request,
    instrument: str | None = None,
) -> ScreeningOut | None:
    from app.db.repository import latest_screening
    from app.screening.phq import get_disclaimer, interpret_phq2

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
    lang = "en"
    return ScreeningOut(
        instrument=str(doc["instrument"]),
        score=score,
        interpretation=interpret_phq2(score, lang),
        disclaimer=get_disclaimer(lang),
        created_at=created_iso,
    )


@router.get("/screening/questions")
async def screening_questions(
    instrument: str = "phq2",
    lang: str = "en",
) -> dict[str, Any]:
    from app.screening.phq import get_disclaimer, get_options, get_questions

    if instrument not in ("phq2", "phq4"):
        raise HTTPException(400, "instrument must be phq2 or phq4")
    ui_lang = lang if lang in ("vi", "en") else "en"
    return {
        "instrument": instrument,
        "questions": get_questions(instrument, ui_lang),
        "options": get_options(ui_lang),
        "disclaimer": get_disclaimer(ui_lang),
    }


# ---------------------------------------------------------------------------
# Conversations
# ---------------------------------------------------------------------------

@router.get("/conversations", response_model=list[ConversationSummary])
async def conversations(
    request: Request,
    session_id: str | None = None,
    session_ids: str | None = None,
    limit: int = 30,
) -> list[ConversationSummary]:
    from app.db.repository import (
        list_conversations,
        list_conversations_by_session_ids,
        list_conversations_for_user,
    )

    from app.auth.repository import is_session_owned_by_user

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
        extra = await list_conversations_by_session_ids(
            db, session_ids=ids, limit=limit
        )
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
        out.append(
            ConversationSummary(
                session_id=sid,
                title=str(doc.get("title") or "Chat"),
                updated_at=updated_iso,
                chat_mode=str(doc.get("chat_mode") or "psychologist"),
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
    session_chat_mode = str(conv.get("chat_mode") or "psychologist")
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
            meta = {**meta, "chat_mode": session_chat_mode}
        else:
            meta = {"chat_mode": session_chat_mode}
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
