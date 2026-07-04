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


def client_ip_from_request(request: Request) -> str | None:
    """Best-effort real client IP.

    Prefers the first hop in X-Forwarded-For (trustworthy only behind a proxy
    such as Render/nginx), falling back to the direct socket peer.
    """
    forwarded = request.headers.get("x-forwarded-for")
    if forwarded:
        first = forwarded.split(",")[0].strip()
        if first:
            return first
    real_ip = request.headers.get("x-real-ip")
    if real_ip and real_ip.strip():
        return real_ip.strip()
    client = request.client
    return client.host if client else None


class ConversationSummary(BaseModel):
    session_id: str = Field(description="Định danh phiên (ổn định phía client).")
    title: str = Field(description="Tiêu đề hội thoại (tự sinh sau lượt đầu tiên).")
    updated_at: str = Field(description="Thời điểm cập nhật gần nhất (ISO 8601).")
    chat_mode: str = CHAT_MODE
    summary: str | None = Field(default=None, description="Tóm tắt hội thoại (nếu có).")
    summary_updated_at: str | None = None

    model_config = {
        "json_schema_extra": {
            "examples": [
                {
                    "session_id": "b3f1c2d4e5f60718",
                    "title": "Cách giảm căng thẳng trước kỳ thi",
                    "updated_at": "2026-07-04T06:45:12+00:00",
                    "chat_mode": "medical",
                    "summary": "Người dùng lo lắng trước kỳ thi, đã gợi ý bài tập thở.",
                    "summary_updated_at": "2026-07-04T06:45:12+00:00",
                }
            ]
        }
    }


class ChatRequest(BaseModel):
    message: str = Field(
        ...,
        min_length=1,
        max_length=8000,
        description="Nội dung tin nhắn của người dùng.",
        examples=["Dạo này tôi khó ngủ và hay lo lắng, tôi nên làm gì?"],
    )
    session_id: str = Field(
        ...,
        min_length=8,
        max_length=128,
        description="Định danh phiên chat. Client tự sinh và giữ ổn định giữa các lượt.",
        examples=["b3f1c2d4e5f60718"],
    )


class ActivitySuggestionOut(BaseModel):
    id: str = Field(description="Mã bài tập.", examples=["breathing_478"])
    title: str = Field(description="Tên bài tập.", examples=["Bài thở 4-7-8"])
    description: str = Field(
        description="Mô tả ngắn về bài tập.",
        examples=["Kỹ thuật thở giúp thư giãn nhanh trong 2 phút."],
    )


class ChatResponse(BaseModel):
    reply: str = Field(description="Câu trả lời của trợ lý.")
    session_id: str = Field(description="Định danh phiên chat.")
    conversation_id: str = Field(description="ObjectId của hội thoại trong MongoDB.")
    assistant_message_id: str | None = Field(
        default=None, description="ID tin nhắn của trợ lý vừa được lưu."
    )
    provider: str = Field(description="Nhà cung cấp LLM đã dùng cho lượt này.")
    message_type: str = "medical"
    suggested_activities: list[ActivitySuggestionOut] = Field(
        default_factory=list, description="Danh sách bài tập được gợi ý (nếu có)."
    )
    metadata: dict[str, Any] | None = Field(
        default=None, description="Metadata bổ sung (agent, nguồn tham khảo, cờ handoff...)."
    )
    support_mode: str = Field(
        default="ai",
        description="Chế độ hỗ trợ: `ai`, `awaiting_support`, `human` hoặc `closed`.",
    )
    assigned_support_name: str | None = Field(
        default=None, description="Tên chuyên viên hỗ trợ được gán (nếu có)."
    )

    model_config = {
        "json_schema_extra": {
            "examples": [
                {
                    "reply": "Mình hiểu cảm giác khó ngủ và lo lắng rất mệt mỏi...",
                    "session_id": "b3f1c2d4e5f60718",
                    "conversation_id": "665f0a1b2c3d4e5f60718293",
                    "assistant_message_id": "665f0a1b2c3d4e5f60718294",
                    "provider": "gemini",
                    "message_type": "medical",
                    "suggested_activities": [
                        {
                            "id": "breathing_478",
                            "title": "Bài thở 4-7-8",
                            "description": "Kỹ thuật thở giúp thư giãn nhanh trong 2 phút.",
                        }
                    ],
                    "metadata": {"agent_name": "RAG_AGENT", "chat_mode": "medical"},
                    "support_mode": "ai",
                    "assigned_support_name": None,
                }
            ]
        }
    }


class HandoffRequestBody(BaseModel):
    session_id: str = Field(
        ..., min_length=8, max_length=128, examples=["b3f1c2d4e5f60718"]
    )
    confirm: bool = Field(
        default=False,
        description="`false`: gửi thông báo xin xác nhận. `true`: xác nhận chuyển giao cho người hỗ trợ.",
        examples=[True],
    )


class ConversationStatusOut(BaseModel):
    session_id: str
    support_mode: str = Field(
        description="Chế độ hỗ trợ hiện tại: `ai`, `awaiting_support`, `human`, `closed`."
    )
    assigned_support_name: str | None = None
    assigned_support_id: str | None = None

    model_config = {
        "json_schema_extra": {
            "examples": [
                {
                    "session_id": "b3f1c2d4e5f60718",
                    "support_mode": "human",
                    "assigned_support_name": "Nguyễn Văn A",
                    "assigned_support_id": "665f0a1b2c3d4e5f60718200",
                }
            ]
        }
    }


class WellnessStartRequest(BaseModel):
    session_id: str = Field(
        ..., min_length=8, max_length=128, examples=["b3f1c2d4e5f60718"]
    )
    activity_id: str = Field(
        ...,
        min_length=2,
        max_length=64,
        description="Mã bài tập cần bắt đầu (xem `/activities/catalog`).",
        examples=["breathing_478"],
    )
    quiet: bool = Field(
        default=False,
        description="Nếu `true`, không lưu/trả về tin nhắn giới thiệu bài tập.",
    )
    lang: str | None = Field(
        None, pattern="^(vi|en)$", description="Ngôn ngữ hiển thị (`vi` hoặc `en`).", examples=["vi"]
    )


class WellnessCompleteRequest(BaseModel):
    session_id: str = Field(
        ..., min_length=8, max_length=128, examples=["b3f1c2d4e5f60718"]
    )
    lang: str | None = Field(None, pattern="^(vi|en)$", examples=["vi"])
    activity_id: str | None = Field(
        None,
        min_length=2,
        max_length=64,
        description="Mã bài tập. Nếu bỏ trống, lấy từ phiên wellness đang hoạt động.",
        examples=["breathing_478"],
    )
    duration_sec: int | None = Field(
        None, ge=1, le=86400, description="Thời lượng thực hiện (giây).", examples=[120]
    )


@router.post(
    "/chat",
    response_model=ChatResponse,
    tags=["Chat"],
    summary="Gửi tin nhắn tới trợ lý Helios",
    description=(
        "Xử lý một lượt hội thoại y tế: định tuyến qua các agent (RAG, tìm kiếm web, "
        "wellness), lưu tin nhắn và trả về câu trả lời kèm gợi ý bài tập.\n\n"
        "- Hoạt động ẩn danh theo `session_id`; gửi kèm `Authorization: Bearer <token>` "
        "để gắn hội thoại vào tài khoản.\n"
        "- Nếu phiên đang ở chế độ `human`, hãy gửi tin nhắn qua WebSocket thay vì endpoint này."
    ),
    responses={
        200: {"description": "Câu trả lời của trợ lý."},
        403: {"description": "Phiên đã đóng (`closed`)."},
        409: {"description": "Phiên đang ở chế độ hỗ trợ người thật (`human`)."},
        429: {"description": "Vượt hạn mức chat trong ngày."},
    },
)
async def chat(req: ChatRequest, request: Request) -> ChatResponse:
    return await _execute_chat(req, request)


class ChatQuotaResponse(BaseModel):
    enabled: bool = Field(description="Cơ chế giới hạn có được bật hay không.")
    allowed: bool = Field(description="Người gọi còn được phép chat hay không.")
    used: int = Field(description="Số lượt đã dùng trong ngày.")
    limit: int = Field(description="Hạn mức tối đa mỗi ngày.")
    remaining: int = Field(description="Số lượt còn lại.")
    resets_at: str | None = Field(
        default=None, description="Thời điểm hạn mức được reset (ISO 8601)."
    )

    model_config = {
        "json_schema_extra": {
            "examples": [
                {
                    "enabled": True,
                    "allowed": True,
                    "used": 3,
                    "limit": 20,
                    "remaining": 17,
                    "resets_at": "2026-07-05T00:00:00+00:00",
                }
            ]
        }
    }


@router.get(
    "/chat/quota",
    response_model=ChatQuotaResponse,
    tags=["Chat"],
    summary="Xem hạn mức chat trong ngày",
    description=(
        "Trả về hạn mức chat còn lại của người gọi (theo tài khoản nếu đã đăng nhập, "
        "ngược lại theo địa chỉ IP). Tài khoản `admin`/`support` không bị giới hạn."
    ),
)
async def chat_quota(request: Request) -> ChatQuotaResponse:
    """Current daily chat quota for the caller (user if logged in, else IP)."""
    from app.cache.chat_rate_limit import peek_quota
    from app.config import get_settings

    settings = get_settings()
    db = get_db(request)
    redis = get_redis(request)
    maybe_user = await resolve_optional_current_user(request, db)

    if maybe_user and maybe_user.get("role") in ("admin", "support"):
        return ChatQuotaResponse(
            enabled=False,
            allowed=True,
            used=0,
            limit=settings.user_daily_chat_limit,
            remaining=settings.user_daily_chat_limit,
        )

    if not settings.enable_user_daily_chat_limit:
        return ChatQuotaResponse(
            enabled=False,
            allowed=True,
            used=0,
            limit=settings.user_daily_chat_limit,
            remaining=settings.user_daily_chat_limit,
        )

    uid: ObjectId | None = None
    if maybe_user:
        raw_uid = maybe_user.get("_id")
        if isinstance(raw_uid, ObjectId):
            uid = raw_uid

    status = await peek_quota(
        redis,
        user_id=str(uid) if uid is not None else None,
        ip=client_ip_from_request(request),
    )
    return ChatQuotaResponse(
        enabled=True,
        allowed=status.allowed,
        used=status.used,
        limit=status.limit,
        remaining=status.remaining,
        resets_at=status.resets_at.isoformat(),
    )


async def _execute_chat(req: ChatRequest, request: Request) -> ChatResponse:
    from app.api.medical_handlers import handle_medical_chat_turn, resolve_conversation
    from app.chat_progress import emit_progress
    from app.conversation.context import (
        load_conversation_summary,
        load_recent_user_questions_from_db,
    )
    from app.conversation.user_memory import (
        load_user_long_term_memory,
        schedule_post_turn_memory_updates,
    )
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

    from app.config import get_settings

    settings = get_settings()
    role = (maybe_user or {}).get("role")
    if (
        settings.enable_user_daily_chat_limit
        and support_mode == "ai"
        and role not in ("admin", "support")
    ):
        from app.cache.chat_rate_limit import check_and_consume

        status = await check_and_consume(
            redis,
            user_id=str(uid) if uid is not None else None,
            ip=client_ip_from_request(request),
        )
        if not status.allowed:
            raise HTTPException(
                status_code=429,
                detail={
                    "code": "DAILY_CHAT_LIMIT_EXCEEDED",
                    "message": (
                        f"Bạn đã đạt giới hạn {status.limit} câu hỏi hôm nay. "
                        "Vui lòng quay lại vào ngày mai."
                    ),
                    "used": status.used,
                    "limit": status.limit,
                    "remaining": status.remaining,
                    "resets_at": status.resets_at.isoformat(),
                },
            )

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
    user_long_term_memory = ""
    if uid is not None:
        user_long_term_memory = await load_user_long_term_memory(db, redis, uid)
    prior_user_questions = await load_recent_user_questions_from_db(
        db,
        cid,
        limit=5,
        exclude_current=req.message,
    )
    reply, meta, assistant_message_id = await handle_medical_chat_turn(
        db,
        session_id=req.session_id,
        conversation_id=cid,
        message=req.message,
        conversation_summary=conversation_summary,
        user_long_term_memory=user_long_term_memory,
        prior_user_questions=prior_user_questions,
    )
    suggested = meta.get("suggested_activities") or []

    if meta.get("agent_name") != "HUMAN_HANDOFF":
        schedule_post_turn_memory_updates(
            db,
            redis,
            session_id=req.session_id,
            conversation_id=cid,
            user_id=uid,
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


@router.post(
    "/handoff/request",
    response_model=ChatResponse,
    tags=["Chat"],
    summary="Yêu cầu chuyển giao cho người hỗ trợ",
    description=(
        "Khởi tạo luồng chuyển giao từ AI sang chuyên viên hỗ trợ là người thật.\n\n"
        "- Gọi lần đầu với `confirm=false` để nhận thông báo xin xác nhận đồng ý.\n"
        "- Gọi lại với `confirm=true` để chính thức đưa phiên vào hàng đợi hỗ trợ "
        "(`awaiting_support`)."
    ),
)
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


@router.get(
    "/conversations/{session_id}/status",
    response_model=ConversationStatusOut,
    tags=["Conversations"],
    summary="Trạng thái hỗ trợ của phiên",
    description=(
        "Trả về chế độ hỗ trợ hiện tại của phiên và thông tin chuyên viên được gán "
        "(nếu đang ở chế độ `human`). Nếu phiên chưa tồn tại, mặc định là `ai`."
    ),
)
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


@router.post(
    "/chat/stream",
    tags=["Chat"],
    summary="Gửi tin nhắn (streaming SSE)",
    description=(
        "Giống `/chat` nhưng trả về luồng **Server-Sent Events** (`text/event-stream`).\n\n"
        "Mỗi sự kiện là một dòng `data: <json>`:\n"
        "- `{\"type\": \"status\", \"step\": \"...\", \"label\": \"...\"}` — bước xử lý hiện tại.\n"
        "- `{\"type\": \"done\", ...}` — kết quả cuối cùng (tương đương `ChatResponse`).\n"
        "- `{\"type\": \"error\", \"message\": \"...\"}` — khi có lỗi.\n\n"
        "Lưu ý: Swagger UI không render tốt SSE; nên thử bằng `curl -N` hoặc `EventSource`."
    ),
    responses={
        200: {
            "content": {
                "text/event-stream": {
                    "example": (
                        'data: {"type": "status", "step": "analyzing_request", '
                        '"label": "Đang phân tích yêu cầu"}\n\n'
                        'data: {"type": "done", "reply": "...", "session_id": "b3f1c2d4e5f60718"}\n\n'
                    )
                }
            }
        }
    },
)
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


@router.post(
    "/wellness/start",
    response_model=ChatResponse,
    tags=["Wellness"],
    summary="Bắt đầu một bài tập wellness",
    description=(
        "Khởi tạo phiên wellness cho một bài tập cụ thể và (tùy chọn) lưu tin nhắn "
        "giới thiệu vào hội thoại. Trả về lỗi 400 nếu `activity_id` không hợp lệ."
    ),
    responses={400: {"description": "Bài tập không tồn tại hoặc không khả dụng."}},
)
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


@router.post(
    "/wellness/complete",
    tags=["Wellness"],
    summary="Hoàn thành bài tập wellness",
    description=(
        "Kết thúc phiên wellness đang hoạt động, ghi nhận lượt hoàn thành và trả về "
        "tin nhắn check-in cùng cờ hiển thị ô đánh giá bài tập."
    ),
    responses={
        200: {
            "content": {
                "application/json": {
                    "example": {
                        "checkin_message": "Bạn vừa hoàn thành bài thở 4-7-8. Cảm giác thế nào?",
                        "show_activity_rating": True,
                        "activity_id": "breathing_478",
                        "completion_id": "665f0a1b2c3d4e5f60718295",
                        "assistant_message_id": "665f0a1b2c3d4e5f60718296",
                        "wellness_session": {"activity_id": "breathing_478", "step": "completed"},
                    }
                }
            }
        }
    },
)
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


@router.get(
    "/conversations",
    response_model=list[ConversationSummary],
    tags=["Conversations"],
    summary="Danh sách hội thoại",
    description=(
        "Trả về danh sách hội thoại của người dùng đã đăng nhập và/hoặc theo các "
        "`session_id` được cung cấp.\n\n"
        "- `session_id`: một phiên đơn lẻ.\n"
        "- `session_ids`: danh sách phiên, phân tách bằng dấu phẩy.\n"
        "- Khi đã đăng nhập, các phiên ẩn danh khớp sẽ được gắn vào tài khoản."
    ),
)
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


@router.delete(
    "/conversations/{session_id}",
    tags=["Conversations"],
    summary="Xóa một hội thoại",
    description=(
        "Xóa hội thoại theo `session_id` cùng dữ liệu cache liên quan. Nếu hội thoại "
        "thuộc về một tài khoản, người gọi phải đăng nhập và là chủ sở hữu."
    ),
    responses={
        200: {"content": {"application/json": {"example": {"status": "deleted"}}}},
        401: {"description": "Cần đăng nhập để xóa hội thoại thuộc tài khoản."},
        403: {"description": "Không phải chủ sở hữu hội thoại."},
    },
)
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
    id: str = Field(description="Mã bài tập.", examples=["breathing_478"])
    title: str = Field(examples=["Bài thở 4-7-8"])
    description: str = Field(examples=["Kỹ thuật thở giúp thư giãn nhanh."])
    content_type: str = Field(examples=["exercise"])
    activity_type: str = Field(examples=["breathing"])
    ui_component: str = Field(
        description="Component UI dùng để hiển thị bài tập.", examples=["BreathingTimer"]
    )
    video_url: str | None = None
    youtube_id: str | None = None
    video_source: ActivityVideoSourceOut | None = None
    duration_min: int = Field(description="Thời lượng gợi ý (phút).", examples=[2])
    avg_rating: float = Field(description="Điểm đánh giá trung bình.", examples=[4.6])
    rating_count: int = Field(description="Số lượt đánh giá.", examples=[128])
    benefits: list[str] = Field(
        default_factory=list, examples=[["Giảm lo âu", "Dễ ngủ hơn"]]
    )
    tags: list[str] = Field(default_factory=list, examples=[["thở", "thư giãn"]])


class ActivityRateBody(BaseModel):
    session_id: str = Field(
        ..., min_length=8, max_length=128, examples=["b3f1c2d4e5f60718"]
    )
    activity_id: str = Field(
        ..., min_length=2, max_length=64, examples=["breathing_478"]
    )
    completion_id: str = Field(
        ...,
        min_length=1,
        description="ID lượt hoàn thành (nhận được từ `/wellness/complete`).",
        examples=["665f0a1b2c3d4e5f60718295"],
    )
    rating: int = Field(
        ..., ge=1, le=5, description="Điểm đánh giá từ 1 đến 5 sao.", examples=[5]
    )
    message_id: str | None = Field(
        None, max_length=32, description="ID tin nhắn chứa ô đánh giá (tùy chọn)."
    )


class MessageOut(BaseModel):
    id: str = Field(description="ID tin nhắn.")
    role: str = Field(description="Vai trò: `user` hoặc `assistant`.")
    content: str = Field(description="Nội dung tin nhắn.")
    created_at: str = Field(description="Thời điểm tạo (ISO 8601).")
    metadata: dict[str, Any] | None = None

    model_config = {
        "json_schema_extra": {
            "examples": [
                {
                    "id": "665f0a1b2c3d4e5f60718294",
                    "role": "assistant",
                    "content": "Mình gợi ý bạn thử bài thở 4-7-8 nhé...",
                    "created_at": "2026-07-04T06:45:12+00:00",
                    "metadata": {"chat_mode": "medical", "sender_name": "Helios"},
                }
            ]
        }
    }


@router.get(
    "/messages",
    response_model=list[MessageOut],
    tags=["Conversations"],
    summary="Lịch sử tin nhắn của phiên",
    description=(
        "Trả về danh sách tin nhắn theo thứ tự thời gian của một phiên. "
        "Trả về mảng rỗng nếu phiên chưa tồn tại."
    ),
)
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
    session_id: str = Field(
        ..., min_length=8, max_length=128, examples=["b3f1c2d4e5f60718"]
    )
    activity_id: str = Field(
        ..., min_length=2, max_length=64, examples=["breathing_478"]
    )
    linked_message_id: str | None = Field(
        None, max_length=32, description="ID tin nhắn liên kết với lượt hoàn thành."
    )
    duration_sec: int | None = Field(
        None, ge=1, le=86400, description="Thời lượng thực hiện (giây).", examples=[120]
    )


class ActivityCompletionOut(BaseModel):
    id: str = Field(description="ID lượt hoàn thành.")
    session_id: str
    activity_id: str
    linked_message_id: str | None = None
    created_at: str

    model_config = {
        "json_schema_extra": {
            "examples": [
                {
                    "id": "665f0a1b2c3d4e5f60718295",
                    "session_id": "b3f1c2d4e5f60718",
                    "activity_id": "breathing_478",
                    "linked_message_id": "665f0a1b2c3d4e5f60718296",
                    "created_at": "2026-07-04T06:50:00+00:00",
                }
            ]
        }
    }


@router.get(
    "/activities/catalog",
    response_model=list[ActivityCatalogOut],
    tags=["Activities"],
    summary="Danh mục bài tập wellness",
    description=(
        "Trả về danh mục bài tập đang bật và đã triển khai. Nếu MongoDB chưa có dữ liệu, "
        "hệ thống dùng danh mục mặc định (seed).\n\n"
        "- `scope`: phạm vi bài tập (mặc định `helios`).\n"
        "- `lang`: ngôn ngữ hiển thị (`vi` hoặc `en`)."
    ),
)
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


@router.post(
    "/activities/rate",
    tags=["Activities"],
    summary="Đánh giá bài tập đã hoàn thành",
    description=(
        "Lưu điểm đánh giá (1–5 sao) cho một lượt hoàn thành bài tập. "
        "Nếu truyền `message_id`, metadata của tin nhắn tương ứng sẽ được cập nhật."
    ),
    responses={
        200: {
            "content": {
                "application/json": {
                    "example": {
                        "status": "ok",
                        "message": "Cảm ơn bạn đã đánh giá!",
                    }
                }
            }
        },
        400: {"description": "`completion_id` không hợp lệ hoặc sai bài tập."},
        403: {"description": "`session_id` không khớp với lượt hoàn thành."},
        404: {"description": "Không tìm thấy lượt hoàn thành."},
    },
)
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


@router.post(
    "/activities/complete",
    response_model=ActivityCompletionOut,
    tags=["Activities"],
    summary="Ghi nhận hoàn thành bài tập",
    description=(
        "Ghi nhận một lượt hoàn thành bài tập độc lập (không qua phiên wellness). "
        "Tự tạo hội thoại nếu phiên chưa tồn tại."
    ),
    responses={400: {"description": "Bài tập hoặc `linked_message_id` không hợp lệ."}},
)
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


@router.get(
    "/activities",
    response_model=list[ActivityCompletionOut],
    tags=["Activities"],
    summary="Lịch sử bài tập đã hoàn thành",
    description="Trả về danh sách các lượt hoàn thành bài tập của một phiên.",
)
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
    text: str = Field(description="Văn bản đã nhận dạng từ audio.")
    language_code: str | None = Field(
        default=None, description="Mã ngôn ngữ được phát hiện (nếu có)."
    )

    model_config = {
        "json_schema_extra": {
            "examples": [
                {"text": "Dạo này tôi hay mất ngủ.", "language_code": "vie"}
            ]
        }
    }


@router.post(
    "/speech/transcribe",
    response_model=SpeechToTextResponse,
    tags=["Speech"],
    summary="Chuyển giọng nói thành văn bản",
    description=(
        "Nhận file audio (multipart/form-data) và trả về văn bản nhận dạng qua ElevenLabs.\n\n"
        "- `audio`: file ghi âm (ví dụ `audio/webm`, `audio/mp3`).\n"
        "- `language_code`: mã ngôn ngữ gợi ý (tùy chọn).\n\n"
        "Yêu cầu cấu hình `ELEVEN_LABS_API_KEY` trên server."
    ),
    responses={
        400: {"description": "File audio rỗng hoặc lỗi nhận dạng."},
        503: {"description": "Chưa cấu hình dịch vụ speech-to-text."},
    },
)
async def transcribe_speech(
    request: Request,
    audio: UploadFile = File(..., description="File audio cần chuyển thành văn bản."),
    language_code: str | None = Form(None, description="Mã ngôn ngữ gợi ý, ví dụ `vie`."),
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
