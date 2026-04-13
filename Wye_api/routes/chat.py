from __future__ import annotations

from typing import Annotated

from bson import ObjectId
from fastapi import APIRouter, Depends, Request, status

from controller.chat_controller import (
    create_message_controller,
    create_session_controller,
    get_current_user_id_controller,
    list_messages_controller,
    list_sessions_controller,
)
from schemas.chat import (
    ConversationResponse,
    CreateConversationRequest,
    CreateMessageRequest,
    MessageResponse,
)

chat_router = APIRouter(prefix="/chat", tags=["Chat"])


@chat_router.get("/sessions", response_model=list[ConversationResponse])
async def list_sessions(
    request: Request,
    user_id: Annotated[ObjectId, Depends(get_current_user_id_controller)],
) -> list[ConversationResponse]:
    return await list_sessions_controller(request, user_id)


@chat_router.post("/sessions", response_model=ConversationResponse, status_code=status.HTTP_201_CREATED)
async def create_session(
    request: Request,
    payload: CreateConversationRequest,
    user_id: Annotated[ObjectId, Depends(get_current_user_id_controller)],
) -> ConversationResponse:
    return await create_session_controller(request, payload, user_id)


@chat_router.get("/sessions/{conversation_id}/messages", response_model=list[MessageResponse])
async def list_messages(
    conversation_id: str,
    request: Request,
    user_id: Annotated[ObjectId, Depends(get_current_user_id_controller)],
) -> list[MessageResponse]:
    return await list_messages_controller(request, conversation_id, user_id)


@chat_router.post(
    "/sessions/{conversation_id}/messages",
    response_model=MessageResponse,
    status_code=status.HTTP_201_CREATED,
)
async def create_message(
    conversation_id: str,
    payload: CreateMessageRequest,
    request: Request,
    user_id: Annotated[ObjectId, Depends(get_current_user_id_controller)],
) -> MessageResponse:
    return await create_message_controller(request, conversation_id, payload, user_id)
