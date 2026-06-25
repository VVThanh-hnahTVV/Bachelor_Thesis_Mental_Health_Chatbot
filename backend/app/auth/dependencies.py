from __future__ import annotations

from typing import Any

from bson import ObjectId
from fastapi import Depends, HTTPException, Request, Security
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from motor.motor_asyncio import AsyncIOMotorDatabase

from app.auth.repository import get_session_link_by_session_id, get_user_by_id
from app.auth.security import bearer_token, decode_access_token

bearer_scheme = HTTPBearer(auto_error=False)


def get_db(request: Request) -> AsyncIOMotorDatabase:
    db = getattr(request.app.state, "db", None)
    if db is None:
        raise HTTPException(503, "Database not ready")
    return db


async def resolve_current_user(
    request: Request,
    db: AsyncIOMotorDatabase,
    credentials: HTTPAuthorizationCredentials | None = None,
) -> dict[str, Any]:
    """Resolve authenticated user from bearer credentials (callable outside FastAPI DI)."""
    token = credentials.credentials if credentials else bearer_token(request)
    if not token:
        raise HTTPException(401, "Not authenticated")
    payload = decode_access_token(token)
    raw_sub = payload.get("sub")
    if not isinstance(raw_sub, str):
        raise HTTPException(401, "Invalid token subject")
    try:
        user_id = ObjectId(raw_sub)
    except Exception as exc:  # noqa: BLE001
        raise HTTPException(401, "Invalid token subject") from exc
    user = await get_user_by_id(db, user_id)
    if not user:
        raise HTTPException(401, "User not found")
    return user


async def resolve_optional_current_user(
    request: Request,
    db: AsyncIOMotorDatabase,
    credentials: HTTPAuthorizationCredentials | None = None,
) -> dict[str, Any] | None:
    """Resolve user when token present; None for anonymous (callable outside FastAPI DI)."""
    token = credentials.credentials if credentials else bearer_token(request)
    if not token:
        return None
    return await resolve_current_user(request, db, credentials)


async def get_current_user(
    request: Request,
    db: AsyncIOMotorDatabase = Depends(get_db),
    credentials: HTTPAuthorizationCredentials | None = Security(bearer_scheme),
) -> dict[str, Any]:
    return await resolve_current_user(request, db, credentials)


async def get_optional_current_user(
    request: Request,
    db: AsyncIOMotorDatabase = Depends(get_db),
    credentials: HTTPAuthorizationCredentials | None = Security(bearer_scheme),
) -> dict[str, Any] | None:
    return await resolve_optional_current_user(request, db, credentials)


async def require_admin_panel(
    user: dict[str, Any] = Depends(get_current_user),
) -> dict[str, Any]:
    if user.get("role") not in ("admin", "support"):
        raise HTTPException(403, "Admin panel access required")
    return user


async def require_admin(
    user: dict[str, Any] = Depends(get_current_user),
) -> dict[str, Any]:
    if user.get("role") != "admin":
        raise HTTPException(403, "Admin only")
    return user


async def ensure_session_ownership(
    *,
    db: AsyncIOMotorDatabase,
    session_id: str,
    user_id: ObjectId,
) -> None:
    link = await get_session_link_by_session_id(db, session_id)
    if not link:
        raise HTTPException(403, "Session is not linked to this user")
    owner = link.get("user_id")
    if not isinstance(owner, ObjectId) or owner != user_id:
        raise HTTPException(403, "Session does not belong to this user")
