from __future__ import annotations

from datetime import UTC, datetime

import jwt
from bson import ObjectId
from fastapi import Depends, HTTPException, Request, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer

from config import get_settings
from db.setup_collections import CONVERSATIONS_COLLECTION, MESSAGES_COLLECTION
from schemas.chat import ConversationResponse, CreateConversationRequest, CreateMessageRequest, MessageResponse
from service.chat_service import persist_user_message_and_reply

security = HTTPBearer(auto_error=False)


def _conversation_payload(document: dict) -> ConversationResponse:
    return ConversationResponse.model_validate(
        {
            "_id": document["_id"],
            "title": document["title"],
            "created_at": document["created_at"],
            "updated_at": document["updated_at"],
            "last_message_preview": document.get("last_message_preview"),
        }
    )


def _message_payload(document: dict) -> MessageResponse:
    return MessageResponse.model_validate(
        {
            "_id": document["_id"],
            "conversation_id": document["conversation_id"],
            "role": document["role"],
            "content": document["content"],
            "created_at": document["created_at"],
        }
    )


def extract_subject_from_jwt(token: str) -> str:
    settings = get_settings()
    try:
        payload = jwt.decode(
            token,
            settings.jwt_secret_key.get_secret_value(),
            algorithms=[settings.jwt_algorithm],
        )
    except jwt.InvalidTokenError as exc:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid token") from exc

    token_type = payload.get("type")
    if token_type != "access":
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid token type")

    subject = payload.get("sub")
    if not isinstance(subject, str) or not ObjectId.is_valid(subject):
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid token subject")
    return subject


async def get_current_user_id_controller(
    request: Request,
    credentials: HTTPAuthorizationCredentials | None = Depends(security),
) -> ObjectId:
    raw_token: str | None = None
    if credentials is not None:
        raw_token = credentials.credentials
    else:
        cookie_token = request.cookies.get("accessToken")
        if isinstance(cookie_token, str) and cookie_token.strip():
            raw_token = cookie_token.strip()

    if raw_token is None:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Authentication required")

    return ObjectId(extract_subject_from_jwt(raw_token))


async def list_sessions_controller(request: Request, user_id: ObjectId) -> list[ConversationResponse]:
    conversations = request.app.state.db[CONVERSATIONS_COLLECTION]
    cursor = conversations.find({"user_id": user_id}).sort("updated_at", -1)
    docs = await cursor.to_list(length=100)
    return [_conversation_payload(doc) for doc in docs]


async def create_session_controller(
    request: Request,
    payload: CreateConversationRequest,
    user_id: ObjectId,
) -> ConversationResponse:
    now = datetime.now(UTC)
    conversations = request.app.state.db[CONVERSATIONS_COLLECTION]
    document = {
        "user_id": user_id,
        "title": payload.title.strip() or "New conversation",
        "created_at": now,
        "updated_at": now,
        "last_message_preview": None,
    }
    insert_result = await conversations.insert_one(document)
    return _conversation_payload({**document, "_id": insert_result.inserted_id})


async def list_messages_controller(
    request: Request,
    conversation_id: str,
    user_id: ObjectId,
) -> list[MessageResponse]:
    if not ObjectId.is_valid(conversation_id):
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Invalid conversation id")

    conversation_obj_id = ObjectId(conversation_id)
    conversations = request.app.state.db[CONVERSATIONS_COLLECTION]
    messages = request.app.state.db[MESSAGES_COLLECTION]

    conversation_doc = await conversations.find_one({"_id": conversation_obj_id, "user_id": user_id})
    if conversation_doc is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Conversation not found")

    cursor = messages.find({"conversation_id": conversation_obj_id, "user_id": user_id}).sort("created_at", 1)
    docs = await cursor.to_list(length=1000)
    return [_message_payload(doc) for doc in docs]


async def create_message_controller(
    request: Request,
    conversation_id: str,
    payload: CreateMessageRequest,
    user_id: ObjectId,
) -> MessageResponse:
    if not ObjectId.is_valid(conversation_id):
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Invalid conversation id")

    conversation_obj_id = ObjectId(conversation_id)
    conversations = request.app.state.db[CONVERSATIONS_COLLECTION]
    messages = request.app.state.db[MESSAGES_COLLECTION]

    conversation_doc = await conversations.find_one({"_id": conversation_obj_id, "user_id": user_id})
    if conversation_doc is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Conversation not found")

    content = payload.content.strip()
    if payload.role == "user":
        user_doc, _assistant_doc = await persist_user_message_and_reply(
            request.app.state.db,
            conversation_id=conversation_obj_id,
            user_id=user_id,
            content=content,
        )
        return _message_payload(user_doc)

    now = datetime.now(UTC)
    document = {
        "conversation_id": conversation_obj_id,
        "user_id": user_id,
        "role": payload.role,
        "content": content,
        "created_at": now,
    }
    insert_result = await messages.insert_one(document)
    await conversations.update_one(
        {"_id": conversation_obj_id, "user_id": user_id},
        {"$set": {"updated_at": now, "last_message_preview": content[:500]}},
    )
    return _message_payload({**document, "_id": insert_result.inserted_id})
