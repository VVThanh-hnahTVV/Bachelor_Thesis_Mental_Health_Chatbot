"""Medical-mode chat handlers (monolith, no sidecar)."""

from __future__ import annotations

from typing import Any, Literal

from bson import ObjectId
from fastapi import HTTPException
from motor.motor_asyncio import AsyncIOMotorDatabase

from app.config import get_settings
from app.db.repository import append_message, create_conversation
from app.medical.service import get_medical_service

ChatMode = Literal["psychologist", "medical"]


def normalize_chat_mode(value: str | None) -> ChatMode:
    if value == "medical":
        return "medical"
    return "psychologist"


async def resolve_conversation_mode(
    db: AsyncIOMotorDatabase,
    *,
    session_id: str,
    requested_mode: str | None,
    conv: dict[str, Any] | None,
    user_id: ObjectId | None = None,
) -> tuple[dict[str, Any], ChatMode]:
    mode = normalize_chat_mode(requested_mode)
    if conv is None:
        conv = await create_conversation(
            db, session_id=session_id, chat_mode=mode, user_id=user_id
        )
        return conv, mode

    stored = normalize_chat_mode(conv.get("chat_mode"))
    if requested_mode and normalize_chat_mode(requested_mode) != stored:
        raise HTTPException(
            400,
            detail="Cannot change chat mode during an active session.",
        )
    return conv, stored


async def handle_medical_chat_turn(
    db: AsyncIOMotorDatabase,
    *,
    session_id: str,
    conversation_id: ObjectId,
    message: str,
    conversation_summary: str = "",
) -> tuple[str, dict[str, Any], str | None]:
    settings = get_settings()
    if not settings.enable_medical_mode:
        raise HTTPException(503, detail="Medical mode is disabled")

    svc = get_medical_service()
    try:
        turn = await svc.handle_message(
            session_id,
            message,
            conversation_summary=conversation_summary,
        )
    except Exception as exc:  # noqa: BLE001
        raise HTTPException(500, detail=f"Medical assistant error: {exc}") from exc

    meta: dict[str, Any] = {
        "chat_mode": "medical",
        "agent_name": turn.agent_name,
        "message_type": "medical",
    }
    if turn.suggested_activities:
        meta["suggested_activities"] = turn.suggested_activities
    if getattr(turn, "wellness_retrieval_score", None) is not None:
        meta["wellness_retrieval_score"] = turn.wellness_retrieval_score
    if getattr(turn, "wellness_retrieval_source", None):
        meta["wellness_retrieval_source"] = turn.wellness_retrieval_source

    assistant_doc = await append_message(
        db,
        conversation_id=conversation_id,
        role="assistant",
        content=turn.reply,
        metadata=meta,
    )
    aid = assistant_doc.get("_id")
    assistant_message_id = str(aid) if aid is not None else None
    return turn.reply, meta, assistant_message_id
