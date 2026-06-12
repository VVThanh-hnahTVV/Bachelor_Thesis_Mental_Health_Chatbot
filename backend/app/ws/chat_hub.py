"""WebSocket chat hub with Redis pub/sub fan-out."""

from __future__ import annotations

import asyncio
import json
import logging
from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import Any

from bson import ObjectId
from fastapi import WebSocket

from app.db.repository import (
    MESSAGE_VISIBILITY_ALL,
    MESSAGE_VISIBILITY_SUPPORT_ONLY,
    append_message,
    get_conversation_by_session,
    get_support_mode,
)
from app.handoff.escalate import publish_ws_event

logger = logging.getLogger(__name__)


def _iso(dt: Any) -> str:
    if isinstance(dt, datetime):
        return dt.replace(tzinfo=UTC).isoformat()
    return str(dt)


def message_event(doc: dict[str, Any]) -> dict[str, Any]:
    meta = doc.get("metadata") if isinstance(doc.get("metadata"), dict) else {}
    return {
        "type": "message",
        "id": str(doc.get("_id") or ""),
        "role": str(doc.get("role") or ""),
        "content": str(doc.get("content") or ""),
        "sender_name": str(meta.get("sender_name") or doc.get("role") or ""),
        "created_at": _iso(doc.get("created_at")),
        "metadata": meta,
    }


def ws_event_audience(payload: dict[str, Any]) -> tuple[bool, bool]:
    """Return (to_user, to_support) for a WebSocket payload."""
    event_type = payload.get("type")
    if event_type == "handoff_brief":
        return False, True

    meta = payload.get("metadata")
    if isinstance(meta, dict):
        if meta.get("visibility") == MESSAGE_VISIBILITY_SUPPORT_ONLY:
            return False, True
        if meta.get("message_type") == "handoff_brief":
            return False, True

    return True, True


@dataclass
class SessionConnections:
    user_ws: WebSocket | None = None
    support_ws: WebSocket | None = None
    listeners: set[asyncio.Task] = field(default_factory=set)


class ChatHub:
    def __init__(self) -> None:
        self._sessions: dict[str, SessionConnections] = {}
        self._lock = asyncio.Lock()

    async def connect(
        self,
        session_id: str,
        websocket: WebSocket,
        role: str,
    ) -> None:
        await websocket.accept()
        async with self._lock:
            conns = self._sessions.setdefault(session_id, SessionConnections())
            if role == "support":
                conns.support_ws = websocket
            else:
                conns.user_ws = websocket

    async def disconnect(self, session_id: str, websocket: WebSocket, role: str) -> None:
        async with self._lock:
            conns = self._sessions.get(session_id)
            if not conns:
                return
            if role == "support" and conns.support_ws is websocket:
                conns.support_ws = None
            elif role == "user" and conns.user_ws is websocket:
                conns.user_ws = None
            if conns.user_ws is None and conns.support_ws is None and not conns.listeners:
                self._sessions.pop(session_id, None)

    async def _send(self, websocket: WebSocket | None, payload: dict[str, Any]) -> None:
        if websocket is None:
            return
        try:
            await websocket.send_json(payload)
        except Exception as exc:  # noqa: BLE001
            logger.debug("ws send failed: %s", exc)

    async def broadcast(
        self,
        session_id: str,
        payload: dict[str, Any],
        *,
        to_user: bool = True,
        to_support: bool = True,
    ) -> None:
        async with self._lock:
            conns = self._sessions.get(session_id)
            if not conns:
                return
            if to_user:
                await self._send(conns.user_ws, payload)
            if to_support:
                await self._send(conns.support_ws, payload)

    async def broadcast_local(self, session_id: str, raw: str) -> None:
        try:
            payload = json.loads(raw)
        except json.JSONDecodeError:
            return
        to_user, to_support = ws_event_audience(payload)
        await self.broadcast(session_id, payload, to_user=to_user, to_support=to_support)

    async def start_redis_listener(self, redis: Any, session_id: str) -> asyncio.Task:
        async def _listen() -> None:
            if redis is None:
                return
            pubsub = redis.pubsub()
            channel = f"ws:session:{session_id}"
            await pubsub.subscribe(channel)
            try:
                async for message in pubsub.listen():
                    if message.get("type") != "message":
                        continue
                    data = message.get("data")
                    if isinstance(data, bytes):
                        data = data.decode("utf-8")
                    if isinstance(data, str):
                        await self.broadcast_local(session_id, data)
            except asyncio.CancelledError:
                raise
            except Exception as exc:  # noqa: BLE001
                logger.warning("redis listener error session=%s: %s", session_id, exc)
            finally:
                try:
                    await pubsub.unsubscribe(channel)
                    await pubsub.close()
                except Exception:  # noqa: BLE001
                    pass

        task = asyncio.create_task(_listen())
        async with self._lock:
            conns = self._sessions.setdefault(session_id, SessionConnections())
            conns.listeners.add(task)
        return task

    async def stop_redis_listener(self, session_id: str, task: asyncio.Task) -> None:
        task.cancel()
        try:
            await task
        except asyncio.CancelledError:
            pass
        async with self._lock:
            conns = self._sessions.get(session_id)
            if conns:
                conns.listeners.discard(task)
                if conns.user_ws is None and conns.support_ws is None and not conns.listeners:
                    self._sessions.pop(session_id, None)


_hub: ChatHub | None = None


def get_chat_hub() -> ChatHub:
    global _hub
    if _hub is None:
        _hub = ChatHub()
    return _hub


async def persist_and_broadcast_message(
    db: Any,
    redis: Any,
    *,
    session_id: str,
    conversation_id: ObjectId,
    role: str,
    content: str,
    sender_name: str,
    sender_id: str | None = None,
    visibility: str = MESSAGE_VISIBILITY_ALL,
    message_type: str = "chat",
) -> dict[str, Any]:
    metadata: dict[str, Any] = {
        "visibility": visibility,
        "sender_name": sender_name,
        "message_type": message_type,
        "chat_mode": "medical",
    }
    if sender_id:
        metadata["sender_id"] = sender_id

    doc = await append_message(
        db,
        conversation_id=conversation_id,
        role=role,
        content=content,
        metadata=metadata,
    )
    event = message_event(doc)
    await publish_ws_event(redis, session_id, event)
    hub = get_chat_hub()
    await hub.broadcast(
        session_id,
        event,
        to_user=visibility != MESSAGE_VISIBILITY_SUPPORT_ONLY,
        to_support=True,
    )
    return doc


async def handle_incoming_ws_message(
    db: Any,
    redis: Any,
    *,
    session_id: str,
    role: str,
    content: str,
    support_user: dict[str, Any] | None,
) -> dict[str, Any] | None:
    content = (content or "").strip()
    if not content:
        return None

    conv = await get_conversation_by_session(db, session_id)
    if not conv:
        return None
    cid = conv.get("_id")
    if not isinstance(cid, ObjectId):
        return None

    mode = get_support_mode(conv)
    if mode != "human":
        return None

    if role == "support":
        if support_user is None:
            return None
        assigned = conv.get("assigned_support_id")
        admin_id = support_user.get("_id")
        if isinstance(assigned, ObjectId) and admin_id != assigned:
            return None
        sender_name = str(support_user.get("name") or support_user.get("email") or "Support")
        sender_id = str(admin_id) if isinstance(admin_id, ObjectId) else None
        return await persist_and_broadcast_message(
            db,
            redis,
            session_id=session_id,
            conversation_id=cid,
            role="support",
            content=content,
            sender_name=sender_name,
            sender_id=sender_id,
        )

    return await persist_and_broadcast_message(
        db,
        redis,
        session_id=session_id,
        conversation_id=cid,
        role="user",
        content=content,
        sender_name="You",
    )
