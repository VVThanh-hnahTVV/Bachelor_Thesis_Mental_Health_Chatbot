"""Medical-mode chat handlers (monolith, no sidecar)."""

from __future__ import annotations

from typing import Any, Literal

from bson import ObjectId
from fastapi import HTTPException, UploadFile
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
) -> tuple[str, dict[str, Any], str | None]:
    settings = get_settings()
    if not settings.enable_medical_mode:
        raise HTTPException(503, detail="Medical mode is disabled")

    svc = get_medical_service()
    try:
        turn = await svc.handle_message(session_id, message)
    except Exception as exc:  # noqa: BLE001
        raise HTTPException(500, detail=f"Medical assistant error: {exc}") from exc

    meta: dict[str, Any] = {
        "chat_mode": "medical",
        "agent_name": turn.agent_name,
        "needs_validation": turn.needs_validation,
        "message_type": "medical",
    }
    if turn.result_image_url:
        meta["result_image"] = turn.result_image_url

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


async def handle_medical_upload_turn(
    db: AsyncIOMotorDatabase,
    *,
    session_id: str,
    conversation_id: ObjectId,
    image: UploadFile,
    text: str,
) -> tuple[str, dict[str, Any], str | None]:
    settings = get_settings()
    if not settings.enable_medical_mode:
        raise HTTPException(503, detail="Medical mode is disabled")

    content = await image.read()
    max_mb = 5
    if len(content) > max_mb * 1024 * 1024:
        raise HTTPException(413, detail=f"File too large. Max {max_mb}MB")

    svc = get_medical_service()
    try:
        turn = await svc.handle_upload(
            session_id,
            content,
            image.filename or "upload.jpg",
            text=text,
        )
    except ValueError as exc:
        raise HTTPException(400, detail=str(exc)) from exc
    except Exception as exc:  # noqa: BLE001
        raise HTTPException(500, detail=f"Medical assistant error: {exc}") from exc

    meta: dict[str, Any] = {
        "chat_mode": "medical",
        "agent_name": turn.agent_name,
        "needs_validation": turn.needs_validation,
        "message_type": "medical",
    }
    if turn.result_image_url:
        meta["result_image"] = turn.result_image_url

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


async def handle_medical_validation_turn(
    db: AsyncIOMotorDatabase,
    *,
    session_id: str,
    conversation_id: ObjectId,
    validation_result: str,
    comments: str | None,
) -> tuple[str, dict[str, Any], str | None]:
    svc = get_medical_service()
    try:
        turn = await svc.handle_validation(session_id, validation_result, comments)
    except Exception as exc:  # noqa: BLE001
        raise HTTPException(500, detail=f"Medical validation error: {exc}") from exc

    meta: dict[str, Any] = {
        "chat_mode": "medical",
        "agent_name": turn.agent_name,
        "needs_validation": turn.needs_validation,
        "message_type": "medical",
        "validation_status": validation_result.lower(),
    }
    if turn.result_image_url:
        meta["result_image"] = turn.result_image_url

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
