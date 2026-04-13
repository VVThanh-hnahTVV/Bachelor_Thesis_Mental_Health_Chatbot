from __future__ import annotations

from datetime import UTC, datetime

from fastapi import APIRouter, HTTPException, Request, status

from db.setup_collections import USERS_COLLECTION
from schemas.users import AuthResponse, LoginRequest, RegisterRequest, UserResponse
from security import (
    create_access_token,
    create_refresh_token,
    hash_password,
    verify_password,
)

auth_router = APIRouter(tags=["Authentication"])


def _to_user_response_payload(document: dict) -> dict:
    return {
        "_id": document["_id"],
        "name": document["name"],
        "email": document["email"],
        "created_at": document["created_at"],
        "updated_at": document["updated_at"],
        "last_login_at": document.get("last_login_at"),
    }

@auth_router.get("/")
async def root():
    return {"message": "Welcome to the Authentication API"}


@auth_router.post("/auth/register", response_model=AuthResponse, status_code=status.HTTP_201_CREATED)
async def register(request: Request, payload: RegisterRequest) -> AuthResponse:
    db = request.app.state.db
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


@auth_router.post("/auth/login", response_model=AuthResponse)
async def login(request: Request, payload: LoginRequest) -> AuthResponse:
    db = request.app.state.db
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