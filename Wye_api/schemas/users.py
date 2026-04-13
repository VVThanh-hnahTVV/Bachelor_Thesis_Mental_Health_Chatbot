from __future__ import annotations

from datetime import datetime

from bson import ObjectId
from pydantic import BaseModel, ConfigDict, EmailStr, Field, field_validator


class PyObjectId(str):
    """String form of Mongo ``ObjectId`` for API responses."""

    @classmethod
    def validate(cls, value: object) -> str:
        if isinstance(value, ObjectId):
            return str(value)
        if isinstance(value, str) and ObjectId.is_valid(value):
            return value
        raise ValueError("Invalid ObjectId")


class RegisterRequest(BaseModel):
    name: str = Field(..., min_length=1, max_length=100)
    email: EmailStr
    password: str = Field(..., min_length=8, max_length=128)

    model_config = ConfigDict(extra="forbid")


class LoginRequest(BaseModel):
    email: EmailStr
    password: str = Field(..., min_length=8, max_length=128)

    model_config = ConfigDict(extra="forbid")


class UserInDB(BaseModel):
    id: str = Field(alias="_id")
    name: str
    email: EmailStr
    password_hash: str
    created_at: datetime
    updated_at: datetime
    last_login_at: datetime | None = None

    model_config = ConfigDict(populate_by_name=True, extra="forbid")

    @field_validator("id", mode="before")
    @classmethod
    def validate_id(cls, value: object) -> str:
        return PyObjectId.validate(value)


class UserResponse(BaseModel):
    id: str = Field(alias="_id")
    name: str
    email: EmailStr
    created_at: datetime
    updated_at: datetime
    last_login_at: datetime | None = None

    model_config = ConfigDict(populate_by_name=True, extra="forbid")

    @field_validator("id", mode="before")
    @classmethod
    def cast_id(cls, value: object) -> str:
        return PyObjectId.validate(value)


class AuthResponse(BaseModel):
    user: UserResponse
    access_token: str
    refresh_token: str
    token_type: str = "Bearer"

    model_config = ConfigDict(extra="forbid")
