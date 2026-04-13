from __future__ import annotations

from datetime import datetime
from typing import Literal

from bson import ObjectId
from pydantic import BaseModel, ConfigDict, Field, field_validator

_EMAIL_PATTERN = r"^[^@\s]+@[^@\s]+\.[^@\s]+$"


class PyObjectId(str):
    """String form of Mongo ``ObjectId`` for API responses."""

    @classmethod
    def validate(cls, value: object) -> str:
        if isinstance(value, ObjectId):
            return str(value)
        if isinstance(value, str) and ObjectId.is_valid(value):
            return value
        raise ValueError("Invalid ObjectId")


class UserSettings(BaseModel):
    reminder_enabled: bool = True
    notification_time: str = Field(
        default="21:00",
        pattern=r"^([01]\d|2[0-3]):[0-5]\d$",
    )

    model_config = ConfigDict(extra="forbid")


class UserBase(BaseModel):
    device_id: str = Field(..., min_length=1)
    platform: Literal["ios", "android", "web"]
    locale: str = Field(default="vi", pattern=r"^[a-z]{2}(-[A-Z]{2})?$")
    settings: UserSettings = Field(default_factory=UserSettings)
    email: str | None = Field(default=None, pattern=_EMAIL_PATTERN)

    model_config = ConfigDict(extra="forbid")


class UserCreate(UserBase):
    """Create payload; hash ``password`` before persisting as ``password_hash``."""

    password: str | None = Field(default=None, min_length=8)
    created_at: datetime = Field(default_factory=datetime.utcnow)
    last_active: datetime = Field(default_factory=datetime.utcnow)

    @field_validator("last_active")
    @classmethod
    def last_active_not_before_created(cls, value: datetime, info) -> datetime:
        created_at = info.data.get("created_at")
        if created_at is not None and value < created_at:
            raise ValueError("last_active must be >= created_at")
        return value


class UserInDB(UserBase):
    """Full user document as stored / loaded from MongoDB."""

    id: str = Field(alias="_id")
    created_at: datetime
    last_active: datetime
    password_hash: str | None = None
    access_token: str | None = None
    refresh_token: str | None = None

    model_config = ConfigDict(populate_by_name=True, extra="forbid")

    @field_validator("id", mode="before")
    @classmethod
    def validate_id(cls, value: object) -> str:
        return PyObjectId.validate(value)


class UserUpdate(BaseModel):
    last_active: datetime | None = None
    locale: str | None = Field(default=None, pattern=r"^[a-z]{2}(-[A-Z]{2})?$")
    settings: UserSettings | None = None
    email: str | None = Field(default=None, pattern=_EMAIL_PATTERN)
    password: str | None = Field(default=None, min_length=8)
    access_token: str | None = None
    refresh_token: str | None = None

    model_config = ConfigDict(extra="forbid")


class UserResponse(UserBase):
    """Safe for clients: no password or tokens."""

    id: str = Field(alias="_id")
    created_at: datetime
    last_active: datetime

    model_config = ConfigDict(populate_by_name=True, extra="forbid")

    @field_validator("id", mode="before")
    @classmethod
    def cast_id(cls, value: object) -> str:
        return PyObjectId.validate(value)


class UserAuthSession(BaseModel):
    """After login / token refresh — includes secrets; do not log or cache carelessly."""

    user: UserResponse
    access_token: str
    refresh_token: str
    token_type: str = "Bearer"

    model_config = ConfigDict(extra="forbid")
