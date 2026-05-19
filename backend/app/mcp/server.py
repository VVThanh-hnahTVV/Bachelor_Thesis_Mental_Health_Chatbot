from __future__ import annotations

from typing import Any, Callable

from bson import ObjectId
from motor.motor_asyncio import AsyncIOMotorDatabase

from app.auth.dependencies import ensure_session_ownership
from app.auth.security import decode_access_token
from app.personalization.context import build_personalization_context


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


def create_personalization_mcp_server(
    *,
    db_getter: Callable[[], AsyncIOMotorDatabase | None],
) -> Any:
    from mcp.server.fastmcp import FastMCP

    mcp = FastMCP("mental-health-personalization")

    async def _load_context(access_token: str, session_id: str) -> dict[str, Any]:
        db = db_getter()
        if db is None:
            raise RuntimeError("Database not ready")
        await _authorize(db, access_token=access_token, session_id=session_id)
        return await build_personalization_context(
            db,
            session_id=session_id,
            include_user_display=True,
        )

    @mcp.tool()
    async def get_user_mood_context(access_token: str, session_id: str) -> dict[str, Any]:
        """Return user mood trend and recent mood highlights."""
        ctx = await _load_context(access_token, session_id)
        return {
            "mood_trend": ctx.get("mood_trend", "stable"),
            "recent_mood_scores": ctx.get("recent_mood_scores", []),
            "recent_mood_notes": ctx.get("recent_mood_notes", []),
        }

    @mcp.tool()
    async def get_user_profile_context(access_token: str, session_id: str) -> dict[str, Any]:
        """Return long-term profile signals for personalized replies."""
        ctx = await _load_context(access_token, session_id)
        return {
            "user_display_name": ctx.get("user_display_name"),
            "preferred_tone": ctx.get("preferred_tone", "warm"),
            "recurring_stressors": ctx.get("recurring_stressors", []),
            "coping_preferences": ctx.get("coping_preferences", []),
        }

    @mcp.tool()
    async def get_personalization_context(access_token: str, session_id: str) -> dict[str, Any]:
        """Return compact context payload for LLM personalization."""
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
