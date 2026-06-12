from __future__ import annotations

import os
from typing import Any

from bson import ObjectId
from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel, EmailStr, Field

from app.auth.email import send_password_reset_email
from app.auth.password_reset import generate_reset_token, hash_token, reset_expires_at
from app.auth.repository import (
    create_user,
    get_user_by_email,
    get_user_by_id,
    get_user_by_reset_token_hash,
    link_session_to_user,
    set_password_reset_token,
    update_user_password,
    user_public,
)
from app.auth.dependencies import get_current_user
from app.auth.security import (
    create_access_token,
    hash_password,
    verify_password,
)
from app.config import get_settings

router = APIRouter(prefix="/api/v1/auth")


class RegisterBody(BaseModel):
    name: str = Field(..., min_length=1, max_length=120)
    email: EmailStr
    password: str = Field(..., min_length=8, max_length=128)
    session_id: str | None = Field(None, min_length=8, max_length=128)


class LoginBody(BaseModel):
    email: EmailStr
    password: str = Field(..., min_length=1, max_length=128)
    session_id: str | None = Field(None, min_length=8, max_length=128)


class LinkSessionBody(BaseModel):
    session_id: str = Field(..., min_length=8, max_length=128)


class ForgotPasswordBody(BaseModel):
    email: EmailStr


class ResetPasswordBody(BaseModel):
    token: str = Field(..., min_length=16, max_length=256)
    password: str = Field(..., min_length=8, max_length=128)


class MessageResponse(BaseModel):
    message: str


class UserOut(BaseModel):
    id: str
    email: str
    name: str
    role: str = "user"


class AuthResponse(BaseModel):
    token: str
    user: UserOut


def get_db(request: Request):
    db = getattr(request.app.state, "db", None)
    if db is None:
        raise HTTPException(503, "Database not ready")
    return db


def _to_user_out(doc: dict[str, Any]) -> UserOut:
    pub = user_public(doc)
    return UserOut(
        id=pub["_id"],
        email=pub["email"],
        name=pub["name"],
        role=pub.get("role", "user"),
    )


def _bootstrap_role_for_email(email: str) -> str:
    bootstrap = (os.getenv("BOOTSTRAP_ADMIN_EMAIL") or "").strip().lower()
    if bootstrap and email.lower().strip() == bootstrap:
        return "admin"
    return "user"


async def _issue_token_and_maybe_link(
    db: Any,
    user: dict[str, Any],
    session_id: str | None,
) -> AuthResponse:
    uid = user["_id"]
    assert isinstance(uid, ObjectId)
    if session_id:
        await link_session_to_user(db, session_id=session_id, user_id=uid)
    token = create_access_token(
        user_id=str(uid),
        email=user["email"],
        name=user["name"],
    )
    return AuthResponse(token=token, user=_to_user_out(user))


@router.post("/register", response_model=AuthResponse)
async def register(body: RegisterBody, request: Request) -> AuthResponse:
    db = get_db(request)
    existing = await get_user_by_email(db, body.email)
    if existing:
        raise HTTPException(409, "Email already registered")
    user = await create_user(
        db,
        email=body.email,
        name=body.name,
        password_hash=hash_password(body.password),
        role=_bootstrap_role_for_email(body.email),
    )
    return await _issue_token_and_maybe_link(db, user, body.session_id)


@router.post("/login", response_model=AuthResponse)
async def login(body: LoginBody, request: Request) -> AuthResponse:
    db = get_db(request)
    user = await get_user_by_email(db, body.email)
    if not user or not verify_password(body.password, user["password_hash"]):
        raise HTTPException(401, "Invalid email or password")
    return await _issue_token_and_maybe_link(db, user, body.session_id)


@router.get("/me", response_model=UserOut)
async def me(user: dict[str, Any] = Depends(get_current_user)) -> UserOut:
    return _to_user_out(user)


@router.post("/forgot-password", response_model=MessageResponse)
async def forgot_password(body: ForgotPasswordBody, request: Request) -> MessageResponse:
    db = get_db(request)
    user = await get_user_by_email(db, body.email)
    if user:
        plain_token, token_hash = generate_reset_token()
        s = get_settings()
        expires_at = reset_expires_at(minutes=s.password_reset_expire_minutes)
        uid = user["_id"]
        assert isinstance(uid, ObjectId)
        await set_password_reset_token(
            db,
            user_id=uid,
            token_hash=token_hash,
            expires_at=expires_at,
        )
        reset_url = f"{s.frontend_url.rstrip('/')}/reset-password?token={plain_token}"
        send_password_reset_email(to_email=user["email"], reset_url=reset_url)
    return MessageResponse(
        message="Nếu tài khoản tồn tại, chúng tôi đã gửi liên kết đặt lại mật khẩu."
    )


@router.post("/reset-password", response_model=MessageResponse)
async def reset_password(body: ResetPasswordBody, request: Request) -> MessageResponse:
    db = get_db(request)
    token_hash = hash_token(body.token)
    user = await get_user_by_reset_token_hash(db, token_hash)
    if not user:
        raise HTTPException(400, "Liên kết đặt lại không hợp lệ hoặc đã hết hạn.")
    uid = user["_id"]
    assert isinstance(uid, ObjectId)
    await update_user_password(
        db,
        user_id=uid,
        password_hash=hash_password(body.password),
    )
    return MessageResponse(message="Đặt lại mật khẩu thành công.")


@router.post("/link-session")
async def link_session(body: LinkSessionBody, request: Request) -> dict[str, str]:
    db = get_db(request)
    user = await get_current_user(request, db)
    uid = user["_id"]
    assert isinstance(uid, ObjectId)
    await link_session_to_user(db, session_id=body.session_id, user_id=uid)
    return {"status": "linked", "session_id": body.session_id}
