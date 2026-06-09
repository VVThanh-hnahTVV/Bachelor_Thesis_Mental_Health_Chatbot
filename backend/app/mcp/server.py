from __future__ import annotations

from typing import Any, Callable

from bson import ObjectId
from motor.motor_asyncio import AsyncIOMotorDatabase

from app.auth.dependencies import ensure_session_ownership
from app.auth.repository import get_session_link_by_session_id, get_user_by_id
from app.auth.security import decode_access_token


async def _authorize(
    db: AsyncIOMotorDatabase,
    *,
    access_token: str,
    session_id: str,
) -> None:
    payload = decode_access_token(access_token)
    raw_sub = payload.get("sub")
    if not isinstance(raw_sub, str):
        raise ValueError("Invalid token subject")
    try:
        user_oid = ObjectId(raw_sub)
    except Exception as exc:  # noqa: BLE001
        raise ValueError("Invalid token subject") from exc
    await ensure_session_ownership(db=db, session_id=session_id, user_id=user_oid)


async def _load_session_context(
    db: AsyncIOMotorDatabase,
    session_id: str,
) -> dict[str, Any]:
    link = await get_session_link_by_session_id(db, session_id)
    context: dict[str, Any] = {"session_id": session_id}
    if link:
        user_oid = link.get("user_id")
        if isinstance(user_oid, ObjectId):
            user = await get_user_by_id(db, user_oid)
            if user and isinstance(user.get("name"), str):
                context["user_display_name"] = user["name"]
    return context


def create_personalization_mcp_server(
    *,
    db_getter: Callable[[], AsyncIOMotorDatabase | None],
) -> Any:
    from mcp.server.fastmcp import FastMCP

    mcp = FastMCP("helios-session")

    async def _load_context(access_token: str, session_id: str) -> dict[str, Any]:
        db = db_getter()
        if db is None:
            raise RuntimeError("Database not ready")
        await _authorize(db, access_token=access_token, session_id=session_id)
        return await _load_session_context(db, session_id)

    @mcp.tool()
    async def get_session_context(access_token: str, session_id: str) -> dict[str, Any]:
        """Return basic session context for Helios integrations."""
        return await _load_context(access_token, session_id)

    return mcp


def create_mcp_asgi_app(
    *,
    db_getter: Callable[[], AsyncIOMotorDatabase | None],
) -> Any:
    server = create_personalization_mcp_server(db_getter=db_getter)
    if hasattr(server, "streamable_http_app"):
        return server.streamable_http_app()
    if hasattr(server, "sse_app"):
        return server.sse_app()
    raise RuntimeError("Unsupported FastMCP transport for current mcp package version")
