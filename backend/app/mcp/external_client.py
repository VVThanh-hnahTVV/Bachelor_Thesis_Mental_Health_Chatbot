from __future__ import annotations

import asyncio
import json
from typing import Any

from fastapi import HTTPException

from app.config import get_settings


def _normalize_server_entry(name: str, cfg: dict[str, Any]) -> dict[str, Any]:
    """Ensure each MCP server entry has a valid transport for langchain-mcp-adapters."""
    normalized = dict(cfg)
    transport = str(normalized.get("transport") or "").strip().lower()
    if not transport and normalized.get("url"):
        transport = "http"
    if transport in {"streamable_http", "streamable-http"}:
        transport = "http"
    if not transport:
        raise HTTPException(
            400,
            (
                f"MCP server '{name}' is missing 'transport'. "
                "Use one of: stdio, sse, websocket, http."
            ),
        )
    allowed = {"stdio", "sse", "websocket", "http"}
    if transport not in allowed:
        raise HTTPException(
            400,
            f"MCP server '{name}' has invalid transport '{transport}'.",
        )
    normalized["transport"] = transport
    return normalized


def _load_servers_config() -> dict[str, dict[str, Any]]:
    raw = get_settings().external_mcp_servers_json.strip() or "{}"
    try:
        parsed = json.loads(raw)
    except json.JSONDecodeError as exc:
        raise HTTPException(400, "Invalid external_mcp_servers_json") from exc
    if not isinstance(parsed, dict):
        raise HTTPException(400, "external_mcp_servers_json must be a JSON object")
    out: dict[str, dict[str, Any]] = {}
    for key, value in parsed.items():
        if isinstance(key, str) and isinstance(value, dict):
            out[key] = _normalize_server_entry(key, value)
    return out


def is_tool_allowed(server: str, tool_name: str) -> bool:
    allowlist_raw = get_settings().external_mcp_allowed_tools
    allowlist = {item.strip() for item in allowlist_raw.split(",") if item.strip()}
    if not allowlist:
        return True
    return tool_name in allowlist or f"{server}.{tool_name}" in allowlist


def _normalize_external_payload(payload: Any) -> dict[str, Any]:
    s = get_settings()
    max_chars = max(200, s.external_mcp_max_response_chars)
    text: str
    if isinstance(payload, str):
        text = payload
    else:
        try:
            text = json.dumps(payload, ensure_ascii=False, default=str)
        except Exception:  # noqa: BLE001
            text = str(payload)
    if len(text) > max_chars:
        text = f"{text[: max_chars - 3]}..."
    return {"text": text}


async def _invoke_tool(tool: Any, args: dict[str, Any]) -> Any:
    if hasattr(tool, "ainvoke"):
        return await tool.ainvoke(args)
    if hasattr(tool, "invoke"):
        return await asyncio.to_thread(tool.invoke, args)
    raise RuntimeError("Tool object does not support invoke/ainvoke")


async def call_external_mcp_tool(
    *,
    server: str,
    tool_name: str,
    args: dict[str, Any],
) -> dict[str, Any]:
    settings = get_settings()
    server_map = _load_servers_config()
    if server not in server_map:
        raise HTTPException(400, f"Unknown MCP server '{server}'")
    if not is_tool_allowed(server, tool_name):
        raise HTTPException(403, "MCP tool is not allowed")

    try:
        from langchain_mcp_adapters.client import MultiServerMCPClient
    except Exception as exc:  # noqa: BLE001
        raise RuntimeError("langchain_mcp_adapters is not available") from exc

    timeout = max(1.0, float(settings.external_mcp_timeout_seconds))
    client = MultiServerMCPClient(server_map)

    try:
        tools = await asyncio.wait_for(
            client.get_tools(server_name=server),
            timeout=timeout,
        )
        selected = next((t for t in tools if getattr(t, "name", "") == tool_name), None)
        if selected is None:
            raise HTTPException(404, f"External MCP tool '{tool_name}' was not found")
        raw = await asyncio.wait_for(_invoke_tool(selected, args), timeout=timeout)
    except HTTPException:
        raise
    except ValueError as exc:
        raise HTTPException(400, str(exc)) from exc
    except asyncio.TimeoutError as exc:
        raise HTTPException(504, "External MCP call timed out") from exc
    except Exception as exc:  # noqa: BLE001
        raise HTTPException(502, f"External MCP call failed: {exc}") from exc

    normalized = _normalize_external_payload(raw)
    return {
        "server": server,
        "tool_name": tool_name,
        "result": normalized["text"],
    }
