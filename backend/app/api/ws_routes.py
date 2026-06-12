"""WebSocket routes for human support chat."""

from __future__ import annotations

import logging
from typing import Any

from bson import ObjectId
from fastapi import APIRouter, Query, WebSocket, WebSocketDisconnect

from app.auth.repository import get_user_by_id
from app.auth.security import decode_access_token
from app.ws.chat_hub import get_chat_hub, handle_incoming_ws_message

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/v1/ws")


def _get_db_from_ws(websocket: WebSocket):
    db = getattr(websocket.app.state, "db", None)
    if db is None:
        raise RuntimeError("Database not ready")
    return db


def _get_redis_from_ws(websocket: WebSocket):
    return getattr(websocket.app.state, "redis", None)


async def _resolve_support_user(db: Any, token: str | None) -> dict[str, Any] | None:
    if not token:
        return None
    try:
        payload = decode_access_token(token)
        raw_sub = payload.get("sub")
        if not isinstance(raw_sub, str):
            return None
        user_id = ObjectId(raw_sub)
    except Exception:  # noqa: BLE001
        return None
    user = await get_user_by_id(db, user_id)
    if not user or user.get("role") != "admin":
        return None
    return user


@router.websocket("/chat")
async def ws_chat(
    websocket: WebSocket,
    session_id: str = Query(..., min_length=8, max_length=128),
    role: str = Query("user"),
    token: str | None = Query(None),
) -> None:
    if role not in ("user", "support"):
        await websocket.close(code=4400)
        return

    db = _get_db_from_ws(websocket)
    redis = _get_redis_from_ws(websocket)
    hub = get_chat_hub()

    support_user: dict[str, Any] | None = None
    if role == "support":
        support_user = await _resolve_support_user(db, token)
        if support_user is None:
            await websocket.close(code=4401)
            return

    await hub.connect(session_id, websocket, role)
    listener = await hub.start_redis_listener(redis, session_id)

    try:
        while True:
            raw = await websocket.receive_json()
            msg_type = str(raw.get("type") or "")
            if msg_type == "ping":
                await websocket.send_json({"type": "pong"})
                continue
            if msg_type != "message":
                continue
            content = str(raw.get("content") or "")
            doc = await handle_incoming_ws_message(
                db,
                redis,
                session_id=session_id,
                role=role,
                content=content,
                support_user=support_user,
            )
            if doc is None and role == "support":
                await websocket.send_json(
                    {"type": "error", "detail": "Cannot send message in current session state"}
                )
    except WebSocketDisconnect:
        pass
    except Exception as exc:  # noqa: BLE001
        logger.warning("ws_chat error session=%s: %s", session_id, exc)
        try:
            await websocket.send_json({"type": "error", "detail": str(exc)})
        except Exception:  # noqa: BLE001
            pass
    finally:
        await hub.stop_redis_listener(session_id, listener)
        await hub.disconnect(session_id, websocket, role)
