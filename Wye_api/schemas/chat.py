from __future__ import annotations

from datetime import datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator

from schemas.users import PyObjectId


class ConversationResponse(BaseModel):
    id: str = Field(alias="_id")
    title: str = Field(..., min_length=1, max_length=120)
    created_at: datetime
    updated_at: datetime
    last_message_preview: str | None = None

    model_config = ConfigDict(populate_by_name=True, extra="forbid")

    @field_validator("id", mode="before")
    @classmethod
    def cast_id(cls, value: object) -> str:
        return PyObjectId.validate(value)


class CreateConversationRequest(BaseModel):
    title: str = Field(default="New conversation", min_length=1, max_length=120)

    model_config = ConfigDict(extra="forbid")


class MessageResponse(BaseModel):
    id: str = Field(alias="_id")
    conversation_id: str
    role: Literal["user", "assistant"]
    content: str
    created_at: datetime

    model_config = ConfigDict(populate_by_name=True, extra="forbid")

    @field_validator("id", "conversation_id", mode="before")
    @classmethod
    def cast_object_ids(cls, value: object) -> str:
        return PyObjectId.validate(value)


class CreateMessageRequest(BaseModel):
    content: str = Field(..., min_length=1, max_length=4000)
    role: Literal["user", "assistant"] = "user"

    model_config = ConfigDict(extra="forbid")
