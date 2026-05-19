"""Node 3: memory_retrieval — gather short-term (Redis), long-term (MongoDB), and RAG chunks."""
from __future__ import annotations

import asyncio
import logging
from typing import Any

from app.config import get_settings
from app.mcp.external_client import call_external_mcp_tool
from app.personalization.context import build_personalization_context
from app.rag.retriever import retrieve_chunks

logger = logging.getLogger(__name__)


async def _get_long_term(db: Any, session_id: str) -> dict[str, Any]:
    if db is None or not session_id:
        return {}
    try:
        return await build_personalization_context(
            db,
            session_id=session_id,
            include_user_display=True,
        )
    except Exception as exc:
        logger.warning("long-term memory retrieval failed: %s", exc)
        return {}


async def _get_external_snippets(state: dict[str, Any]) -> tuple[list[str], dict[str, Any]]:
    s = get_settings()
    if not s.enable_graph_external_enrichment:
        return [], {"enabled": False}
    server = (s.graph_external_mcp_server or "").strip()
    tool_name = (s.graph_external_mcp_tool or "").strip()
    if not server or not tool_name:
        return [], {"enabled": True, "configured": False}

    user_input: str = state.get("user_input", "")
    session_id: str = state.get("session_id", "")
    tool_args = {
        "query": user_input,
        "session_id": session_id,
        "intent": state.get("intent"),
    }
    try:
        response = await call_external_mcp_tool(
            server=server,
            tool_name=tool_name,
            args=tool_args,
        )
        snippet = str(response.get("result") or "").strip()
        if not snippet:
            return [], {"enabled": True, "configured": True, "used": False}
        return [f"[external:{server}.{tool_name}] {snippet}"], {
            "enabled": True,
            "configured": True,
            "used": True,
        }
    except Exception as exc:  # noqa: BLE001
        logger.warning("external MCP retrieval failed: %s", exc)
        return [], {"enabled": True, "configured": True, "used": False, "error": str(exc)}


async def node_memory_retrieval(state: dict[str, Any]) -> dict[str, Any]:
    user_input: str = state.get("user_input", "")
    session_id: str = state.get("session_id", "")
    db: Any = state.get("db")

    # RAG (Mongo vector retrieval with lexical fallback)
    rag_chunks, retrieval_mode = await retrieve_chunks(db, user_input)
    retrieved = [c["text"] for c in rag_chunks]

    # Long-term context (prefer cached/prefetched state, fallback DB)
    preloaded = state.get("personalization_context")
    if isinstance(preloaded, dict) and preloaded:
        long_term_task = asyncio.create_task(asyncio.sleep(0, result=preloaded))
    else:
        long_term_task = asyncio.create_task(_get_long_term(db, session_id))
    external_task = asyncio.create_task(_get_external_snippets(state))
    long_term, (external_snippets, external_meta) = await asyncio.gather(
        long_term_task, external_task
    )
    retrieved.extend(external_snippets)

    meta = dict(state.get("metadata") or {})
    meta["retrieve_scores"] = [float(c["score"]) for c in rag_chunks]
    meta["retrieval_mode"] = retrieval_mode
    meta["retrieved_chunks"] = [
        {
            "id": c["id"],
            "topic": c["topic"],
            "score": c["score"],
            "source": c["source"],
        }
        for c in rag_chunks
    ]
    meta["external_mcp"] = external_meta
    return {
        "retrieved_chunks": retrieved,
        "long_term_context": long_term,
        "metadata": meta,
    }
