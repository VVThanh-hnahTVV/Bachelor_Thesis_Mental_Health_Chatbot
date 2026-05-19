from __future__ import annotations

from datetime import UTC, datetime
from typing import Any

from bson import ObjectId
from fastapi import APIRouter, Depends, HTTPException, Security
from fastapi.security import HTTPAuthorizationCredentials
from pydantic import BaseModel, Field

from app.auth.dependencies import (
    bearer_scheme,
    ensure_session_ownership,
    get_current_user,
    get_db,
)
from app.config import get_settings
from app.mcp.external_client import call_external_mcp_tool

router = APIRouter(prefix="/api/v1/mcp", tags=["mcp"])


class ExternalMCPCallRequest(BaseModel):
    session_id: str = Field(..., min_length=8, max_length=128)
    server: str = Field(..., min_length=1, max_length=128)
    tool_name: str = Field(..., min_length=1, max_length=128)
    args: dict[str, Any] = Field(default_factory=dict)


class ExternalMCPCallResponse(BaseModel):
    server: str
    tool_name: str
    result: str
    metadata: dict[str, Any]


@router.post("/external/call", response_model=ExternalMCPCallResponse)
async def external_mcp_call(
    body: ExternalMCPCallRequest,
    _: HTTPAuthorizationCredentials | None = Security(bearer_scheme),
    user: dict[str, Any] = Depends(get_current_user),
    db: Any = Depends(get_db),
) -> ExternalMCPCallResponse:
    s = get_settings()
    if not s.enable_external_mcp_gateway:
        raise HTTPException(404, "External MCP gateway is disabled")

    uid = user.get("_id")
    if not isinstance(uid, ObjectId):
        raise HTTPException(401, "Invalid user id")
    await ensure_session_ownership(db=db, session_id=body.session_id, user_id=uid)

    started_at = datetime.now(UTC)
    result = await call_external_mcp_tool(
        server=body.server,
        tool_name=body.tool_name,
        args=body.args,
    )
    finished_at = datetime.now(UTC)
    elapsed_ms = int((finished_at - started_at).total_seconds() * 1000)
    return ExternalMCPCallResponse(
        server=result["server"],
        tool_name=result["tool_name"],
        result=result["result"],
        metadata={
            "elapsed_ms": elapsed_ms,
            "called_at": started_at.isoformat(),
            "session_id": body.session_id,
        },
    )
