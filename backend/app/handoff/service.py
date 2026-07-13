"""Support join/leave orchestration."""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any

from bson import ObjectId

from app.conversation.summary_markdown import (
    generate_handoff_brief,
    generate_merged_conversation_summary,
)
from app.conversation.episodic_memory import (
    retrieve_relevant_session_memories,
    schedule_finalize_session_memory,
)
from app.auth.repository import resolve_user_id_for_session
from app.db.repository import (
    MESSAGE_VISIBILITY_ALL,
    MESSAGE_VISIBILITY_SUPPORT_ONLY,
    count_user_messages,
    get_conversation_by_session,
    get_conversation_summary,
    get_latest_handoff_brief,
    get_support_mode,
    list_messages_chronological,
    list_messages_since,
    try_claim_human_support,
    update_conversation_summary,
    update_conversation_support_mode,
)
from app.handoff.escalate import publish_ws_event
from app.handoff.messages import support_joined_notice, support_left_notice
from app.llm.factory import default_provider
from app.ws.chat_hub import persist_and_broadcast_message

SESSION_TAKEN_ERROR = "Phiên này đã có chuyên viên khác đang hỗ trợ."


def _join_response(
    *,
    session_id: str,
    support_name: str,
    handoff_brief: str,
    rejoined: bool = False,
) -> dict[str, Any]:
    return {
        "session_id": session_id,
        "support_mode": "human",
        "assigned_support_name": support_name,
        "handoff_brief": handoff_brief,
        "rejoined": rejoined,
    }


async def _resume_support_session(
    db: Any,
    conv: dict[str, Any],
    *,
    session_id: str,
    support_name: str,
) -> dict[str, Any]:
    cid = conv["_id"]
    assert isinstance(cid, ObjectId)
    brief = await get_latest_handoff_brief(db, conversation_id=cid) or ""
    assigned_name = str(conv.get("assigned_support_name") or support_name)
    return _join_response(
        session_id=session_id,
        support_name=assigned_name,
        handoff_brief=brief,
        rejoined=True,
    )


async def join_support_session(
    db: Any,
    redis: Any,
    *,
    session_id: str,
    admin_user: dict[str, Any],
) -> dict[str, Any]:
    conv = await get_conversation_by_session(db, session_id)
    if not conv:
        raise ValueError("Conversation not found")

    mode = get_support_mode(conv)
    if mode == "closed":
        raise ValueError("Session is closed")
    if mode not in ("ai", "awaiting_support", "human"):
        raise ValueError(f"Cannot join session in mode: {mode}")

    cid = conv["_id"]
    assert isinstance(cid, ObjectId)

    admin_id = admin_user.get("_id")
    if not isinstance(admin_id, ObjectId):
        raise ValueError("Invalid admin user")

    support_name = str(admin_user.get("name") or admin_user.get("email") or "Support")
    now = datetime.now(UTC)
    assigned = conv.get("assigned_support_id")

    if mode == "human":
        if isinstance(assigned, ObjectId) and assigned == admin_id:
            return await _resume_support_session(
                db,
                conv,
                session_id=session_id,
                support_name=support_name,
            )
        if isinstance(assigned, ObjectId):
            raise ValueError(SESSION_TAKEN_ERROR)

    handoff_at = conv.get("handoff_requested_at")
    handoff_dt = handoff_at if isinstance(handoff_at, datetime) else now
    claimed = await try_claim_human_support(
        db,
        conversation_id=cid,
        admin_id=admin_id,
        support_name=support_name,
        now=now,
        handoff_requested_at=handoff_dt,
    )
    if not claimed:
        conv = await get_conversation_by_session(db, session_id)
        if not conv:
            raise ValueError("Conversation not found")
        assigned = conv.get("assigned_support_id")
        if get_support_mode(conv) == "human" and isinstance(assigned, ObjectId):
            if assigned == admin_id:
                return await _resume_support_session(
                    db,
                    conv,
                    session_id=session_id,
                    support_name=support_name,
                )
            raise ValueError(SESSION_TAKEN_ERROR)
        raise ValueError("Không thể tham gia phiên này.")

    ai_summary = await get_conversation_summary(db, session_id)
    transcript = await list_messages_chronological(
        db, conversation_id=cid, limit=500, include_support_only=False
    )

    user_long_term_memory = ""
    user_id = await resolve_user_id_for_session(db, session_id)
    if user_id is not None:
        # Past sessions relevant to this one, for the counselor brief.
        user_long_term_memory = await retrieve_relevant_session_memories(
            db,
            user_id=user_id,
            query_text=(ai_summary or "").strip()
            or " ".join(
                str(m.get("content") or "")
                for m in transcript[-6:]
                if str(m.get("role") or "") == "user"
            ),
            exclude_session_id=session_id,
        )

    brief = ""
    try:
        brief = await generate_handoff_brief(
            ai_summary=ai_summary,
            transcript_messages=transcript,
            user_long_term_memory=user_long_term_memory,
            provider=default_provider(),
        )
    except Exception:  # noqa: BLE001
        summary_text = (ai_summary or "").strip() or "(Chưa có tóm tắt AI)"
        brief = (
            "## Tóm tắt nhanh\n"
            f"{summary_text}\n\n"
            "## Gợi ý cho chuyên viên\n"
            "- Xem lại lịch sử chat bên dưới trước khi trả lời."
        )

    if not brief.strip():
        brief = (
            "## Tóm tắt nhanh\n"
            "(Không tạo được brief tự động — vui lòng đọc lịch sử chat.)\n"
        )

    await persist_and_broadcast_message(
        db,
        redis,
        session_id=session_id,
        conversation_id=cid,
        role="system",
        content=brief,
        sender_name="Handoff Brief",
        visibility=MESSAGE_VISIBILITY_SUPPORT_ONLY,
        message_type="handoff_brief",
    )

    user_lang = "vi"
    notice = support_joined_notice(support_name, user_lang)
    await persist_and_broadcast_message(
        db,
        redis,
        session_id=session_id,
        conversation_id=cid,
        role="system",
        content=notice,
        sender_name=support_name,
        sender_id=str(admin_id),
        visibility=MESSAGE_VISIBILITY_ALL,
        message_type="system_notice",
    )

    await publish_ws_event(
        redis,
        session_id,
        {
            "type": "support_joined",
            "support_name": support_name,
            "support_id": str(admin_id),
        },
    )
    await publish_ws_event(
        redis,
        session_id,
        {
            "type": "handoff_brief",
            "content": brief,
            "session_id": session_id,
        },
    )

    return _join_response(
        session_id=session_id,
        support_name=support_name,
        handoff_brief=brief,
        rejoined=False,
    )


async def leave_support_session(
    db: Any,
    redis: Any,
    *,
    session_id: str,
    admin_user: dict[str, Any],
) -> dict[str, Any]:
    conv = await get_conversation_by_session(db, session_id)
    if not conv:
        raise ValueError("Conversation not found")

    mode = get_support_mode(conv)
    if mode != "human":
        raise ValueError(f"Cannot leave session in mode: {mode}")

    cid = conv["_id"]
    assert isinstance(cid, ObjectId)

    admin_id = admin_user.get("_id")
    assigned = conv.get("assigned_support_id")
    if isinstance(assigned, ObjectId) and admin_id != assigned:
        raise ValueError(SESSION_TAKEN_ERROR)

    started = conv.get("human_session_started_at")
    human_messages: list[dict[str, Any]] = []
    if isinstance(started, datetime):
        human_messages = await list_messages_since(
            db,
            conversation_id=cid,
            since=started,
            roles=["user", "support"],
        )

    summary = ""
    if human_messages:
        previous = await get_conversation_summary(db, session_id)
        summary = await generate_merged_conversation_summary(
            previous_summary=previous,
            human_messages=human_messages,
            provider=default_provider(),
        )
        # Merged summary covers every turn so far — move the watermark with it.
        covered = await count_user_messages(db, cid)
        await update_conversation_summary(db, cid, summary, covered_turns=covered)
        if redis is not None:
            from app.cache.session_memory import set_conversation_summary_cache

            await set_conversation_summary_cache(redis, session_id, summary)

        # Counselor left: fold this session into the user's episodic memory.
        schedule_finalize_session_memory(
            db, redis, session_id=session_id, reason="handoff_leave"
        )

    now = datetime.now(UTC)
    notice = support_left_notice("vi")
    support_name = str(conv.get("assigned_support_name") or "Support")
    await persist_and_broadcast_message(
        db,
        redis,
        session_id=session_id,
        conversation_id=cid,
        role="system",
        content=notice,
        sender_name=support_name,
        visibility=MESSAGE_VISIBILITY_ALL,
        message_type="system_notice",
    )

    await update_conversation_support_mode(
        db,
        cid,
        "ai",
        extra={
            "human_session_ended_at": now,
            "assigned_support_id": None,
            "assigned_support_name": None,
        },
    )

    await publish_ws_event(
        redis,
        session_id,
        {
            "type": "support_left",
            "summary": summary or None,
        },
    )

    return {
        "session_id": session_id,
        "support_mode": "ai",
        "summary": summary or None,
    }
