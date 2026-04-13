from __future__ import annotations

from collections.abc import Mapping
from datetime import datetime
from typing import Any

import jwt
import socketio
from bson import ObjectId
from fastapi import FastAPI

from config import get_settings
from db.setup_collections import CONVERSATIONS_COLLECTION
from service.chat_service import persist_user_message_and_reply


def _decode_access_token(token: str) -> ObjectId:
    settings = get_settings()
    payload = jwt.decode(
        token,
        settings.jwt_secret_key.get_secret_value(),
        algorithms=[settings.jwt_algorithm],
    )
    if payload.get("type") != "access":
        raise jwt.InvalidTokenError("Invalid token type")
    subject = payload.get("sub")
    if not isinstance(subject, str) or not ObjectId.is_valid(subject):
        raise jwt.InvalidTokenError("Invalid subject")
    return ObjectId(subject)


def _serialize_message(doc: dict) -> dict[str, Any]:
    created_at = doc.get("created_at")
    created_at_value = created_at.isoformat() if isinstance(created_at, datetime) else datetime.utcnow().isoformat()
    return {
        "id": str(doc["_id"]),
        "sessionId": str(doc["conversation_id"]),
        "role": doc["role"],
        "content": doc["content"],
        "createdAt": created_at_value,
    }


def create_socket_app(app: FastAPI) -> socketio.ASGIApp:
    sio = socketio.AsyncServer(
        async_mode="asgi",
        cors_allowed_origins=[
            "http://localhost:3000",
            "http://127.0.0.1:3000",
        ],
    )

    @sio.event
    async def connect(sid: str, _environ: dict, auth: Mapping[str, Any] | None):  # type: ignore[override]
        token = auth.get("accessToken") if auth else None
        if not isinstance(token, str) or not token.strip():
            return False
        try:
            user_id = _decode_access_token(token.strip())
        except jwt.InvalidTokenError:
            return False
        await sio.save_session(sid, {"user_id": str(user_id)})
        return True

    @sio.event
    async def message_send(sid: str, payload: Mapping[str, Any] | None):
        if not payload:
            await sio.emit("message:error", {"message": "Payload is required"}, room=sid)
            return
        session_id = payload.get("sessionId")
        content = payload.get("content")
        if not isinstance(session_id, str) or not ObjectId.is_valid(session_id):
            await sio.emit("message:error", {"message": "Invalid sessionId"}, room=sid)
            return
        if not isinstance(content, str) or not content.strip():
            await sio.emit("message:error", {"message": "Content is required"}, room=sid)
            return

        session = await sio.get_session(sid)
        user_id_raw = session.get("user_id")
        if not isinstance(user_id_raw, str) or not ObjectId.is_valid(user_id_raw):
            await sio.emit("message:error", {"message": "Unauthorized socket session"}, room=sid)
            return

        db = app.state.db
        conversation_id = ObjectId(session_id)
        user_id = ObjectId(user_id_raw)
        conversation = await db[CONVERSATIONS_COLLECTION].find_one({"_id": conversation_id, "user_id": user_id})
        if conversation is None:
            await sio.emit("message:error", {"message": "Conversation not found"}, room=sid)
            return

        user_doc, assistant_doc = await persist_user_message_and_reply(
            db,
            conversation_id=conversation_id,
            user_id=user_id,
            content=content.strip(),
        )
        await sio.emit("message:sent", _serialize_message(user_doc), room=sid)
        await sio.emit("message:receive", _serialize_message(assistant_doc), room=sid)

    @sio.on("message:send")
    async def on_message_send(sid: str, payload: Mapping[str, Any] | None):
        await message_send(sid, payload)

    return socketio.ASGIApp(sio, other_asgi_app=app)
