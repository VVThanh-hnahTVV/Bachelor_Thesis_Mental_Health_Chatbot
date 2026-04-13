from __future__ import annotations

from datetime import UTC, datetime

import jwt
from bson import ObjectId
from fastapi import HTTPException, status
from motor.motor_asyncio import AsyncIOMotorDatabase

from config import get_settings
from db.setup_collections import USERS_COLLECTION
from schemas.users import AuthResponse, LoginRequest, RefreshTokenResponse, RegisterRequest, UserResponse
from security import create_access_token, create_refresh_token, hash_password, verify_password


def _to_user_response_payload(document: dict) -> dict:
    return {
        "_id": document["_id"],
        "name": document["name"],
        "email": document["email"],
        "created_at": document["created_at"],
        "updated_at": document["updated_at"],
        "last_login_at": document.get("last_login_at"),
    }


def decode_refresh_token(token: str) -> str:
    settings = get_settings()
    try:
        payload = jwt.decode(
            token,
            settings.jwt_secret_key.get_secret_value(),
            algorithms=[settings.jwt_algorithm],
        )
    except jwt.InvalidTokenError as exc:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid refresh token") from exc

    if payload.get("type") != "refresh":
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid refresh token type")

    subject = payload.get("sub")
    if not isinstance(subject, str) or not ObjectId.is_valid(subject):
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid refresh token subject")
    return subject


async def register_user(db: AsyncIOMotorDatabase, payload: RegisterRequest) -> AuthResponse:
    users = db[USERS_COLLECTION]
    email = payload.email.strip().lower()
    now = datetime.now(UTC)

    existing_user = await users.find_one({"email": email}, projection={"_id": 1})
    if existing_user is not None:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Email already registered")

    document = {
        "name": payload.name.strip(),
        "email": email,
        "password_hash": hash_password(payload.password),
        "created_at": now,
        "updated_at": now,
        "last_login_at": now,
    }
    insert_result = await users.insert_one(document)
    user_doc = {**document, "_id": insert_result.inserted_id}

    access_token = create_access_token(str(insert_result.inserted_id))
    refresh_token = create_refresh_token(str(insert_result.inserted_id))
    user = UserResponse.model_validate(_to_user_response_payload(user_doc))
    return AuthResponse(user=user, access_token=access_token, refresh_token=refresh_token)


async def login_user(db: AsyncIOMotorDatabase, payload: LoginRequest) -> AuthResponse:
    users = db[USERS_COLLECTION]
    email = payload.email.strip().lower()

    user_doc = await users.find_one({"email": email})
    if user_doc is None:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid email or password")

    password_hash = user_doc.get("password_hash")
    if not isinstance(password_hash, str) or not verify_password(payload.password, password_hash):
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid email or password")

    now = datetime.now(UTC)
    await users.update_one({"_id": user_doc["_id"]}, {"$set": {"last_login_at": now, "updated_at": now}})
    user_doc["last_login_at"] = now
    user_doc["updated_at"] = now

    access_token = create_access_token(str(user_doc["_id"]))
    refresh_token = create_refresh_token(str(user_doc["_id"]))
    user = UserResponse.model_validate(_to_user_response_payload(user_doc))
    return AuthResponse(user=user, access_token=access_token, refresh_token=refresh_token)


async def refresh_access_token(db: AsyncIOMotorDatabase, refresh_token: str) -> RefreshTokenResponse:
    users = db[USERS_COLLECTION]
    subject = decode_refresh_token(refresh_token)
    user_doc = await users.find_one({"_id": ObjectId(subject)})
    if user_doc is None:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="User not found")
    return RefreshTokenResponse(access_token=create_access_token(subject))
