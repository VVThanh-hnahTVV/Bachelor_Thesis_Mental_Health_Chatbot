from types import SimpleNamespace

import pytest
from fastapi import HTTPException

from app.mcp.external_client import (
    _load_servers_config,
    _normalize_server_entry,
    call_external_mcp_tool,
    is_tool_allowed,
)


def test_normalize_server_entry_defaults_transport_to_http():
    cfg = _normalize_server_entry("medical", {"url": "http://127.0.0.1:9001/mcp"})
    assert cfg["transport"] == "http"


def test_load_servers_config_applies_transport_default(monkeypatch):
    monkeypatch.setattr(
        "app.mcp.external_client.get_settings",
        lambda: SimpleNamespace(
            external_mcp_servers_json='{"medical":{"url":"http://127.0.0.1:9001/mcp"}}',
        ),
    )
    cfg = _load_servers_config()
    assert cfg["medical"]["transport"] == "http"


def test_is_tool_allowed_with_empty_allowlist(monkeypatch):
    monkeypatch.setattr(
        "app.mcp.external_client.get_settings",
        lambda: SimpleNamespace(external_mcp_allowed_tools=""),
    )
    assert is_tool_allowed("medical", "search_articles")


def test_is_tool_allowed_with_scoped_allowlist(monkeypatch):
    monkeypatch.setattr(
        "app.mcp.external_client.get_settings",
        lambda: SimpleNamespace(
            external_mcp_allowed_tools="medical.search_articles,weather.current"
        ),
    )
    assert is_tool_allowed("medical", "search_articles")
    assert not is_tool_allowed("medical", "other_tool")


@pytest.mark.asyncio
async def test_call_external_mcp_tool_without_context_manager(monkeypatch):
    class FakeTool:
        name = "search_articles"

        async def ainvoke(self, args):
            return {"ok": True, "args": args}

    class FakeClient:
        async def get_tools(self, *, server_name=None):
            assert server_name == "medical"
            return [FakeTool()]

    class FakeMultiServerMCPClient:
        def __init__(self, _server_map):
            pass

    monkeypatch.setattr(
        "app.mcp.external_client.get_settings",
        lambda: SimpleNamespace(
            external_mcp_servers_json=(
                '{"medical":{"transport":"http","url":"http://localhost:9001/mcp"}}'
            ),
            external_mcp_allowed_tools="",
            external_mcp_timeout_seconds=6.0,
            external_mcp_max_response_chars=2000,
        ),
    )
    async def fake_get_tools(self, *, server_name=None):
        return [FakeTool()]

    FakeMultiServerMCPClient.get_tools = fake_get_tools
    monkeypatch.setattr(
        "langchain_mcp_adapters.client.MultiServerMCPClient",
        FakeMultiServerMCPClient,
    )

    out = await call_external_mcp_tool(
        server="medical",
        tool_name="search_articles",
        args={"query": "sleep"},
    )
    assert out["server"] == "medical"
    assert out["tool_name"] == "search_articles"
    assert "ok" in out["result"]


@pytest.mark.asyncio
async def test_call_external_mcp_tool_unknown_server(monkeypatch):
    monkeypatch.setattr(
        "app.mcp.external_client.get_settings",
        lambda: SimpleNamespace(
            external_mcp_servers_json="{}",
            external_mcp_allowed_tools="",
            external_mcp_timeout_seconds=6.0,
            external_mcp_max_response_chars=2000,
        ),
    )
    with pytest.raises(HTTPException) as exc:
        await call_external_mcp_tool(
            server="medical",
            tool_name="search_articles",
            args={},
        )
    assert exc.value.status_code == 400
