"""Medical chat service — wraps vendored LangGraph in async-friendly API."""

from __future__ import annotations

import asyncio
import logging
from typing import Any

from langchain_core.messages import AIMessage, BaseMessage

from app.medical.agents.agent_decision import process_query

logger = logging.getLogger(__name__)


class MedicalTurnResult:
    __slots__ = (
        "reply",
        "agent_name",
        "suggested_activities",
        "wellness_retrieval_score",
        "wellness_retrieval_source",
        "rag_sources",
    )

    def __init__(
        self,
        reply: str,
        agent_name: str,
        suggested_activities: list[dict[str, str]] | None = None,
        wellness_retrieval_score: float | None = None,
        wellness_retrieval_source: str | None = None,
        rag_sources: list[dict[str, str]] | None = None,
    ) -> None:
        self.reply = reply
        self.agent_name = agent_name
        self.suggested_activities = suggested_activities or []
        self.wellness_retrieval_score = wellness_retrieval_score
        self.wellness_retrieval_source = wellness_retrieval_source
        self.rag_sources = rag_sources or []


def _extract_reply(result: dict[str, Any]) -> str:
    output = result.get("output")
    if isinstance(output, AIMessage):
        return str(output.content or "")
    if isinstance(output, str):
        return output
    messages = result.get("messages") or []
    if messages:
        last = messages[-1]
        if isinstance(last, AIMessage):
            return str(last.content or "")
        if hasattr(last, "content"):
            return str(last.content)
    return ""


def _agent_name(result: dict[str, Any]) -> str:
    return str(result.get("agent_name") or "MEDICAL")


def _run_sync(
    query: str,
    *,
    thread_id: str,
    conversation_summary: str = "",
    user_long_term_memory: str = "",
    prior_user_questions: list[str] | None = None,
) -> MedicalTurnResult:
    result = process_query(
        query,
        thread_id=thread_id,
        conversation_summary=conversation_summary,
        user_long_term_memory=user_long_term_memory,
        prior_user_questions=prior_user_questions,
    )
    return MedicalTurnResult(
        reply=_extract_reply(result),
        agent_name=_agent_name(result),
        suggested_activities=result.get("suggested_activities") or [],
        wellness_retrieval_score=result.get("wellness_retrieval_score"),
        wellness_retrieval_source=result.get("wellness_retrieval_source"),
        rag_sources=result.get("rag_sources") or [],
    )


class MedicalChatService:
    async def handle_message(
        self,
        session_id: str,
        message: str,
        *,
        conversation_summary: str = "",
        user_long_term_memory: str = "",
        prior_user_questions: list[str] | None = None,
    ) -> MedicalTurnResult:
        return await asyncio.to_thread(
            _run_sync,
            message,
            thread_id=session_id,
            conversation_summary=conversation_summary,
            user_long_term_memory=user_long_term_memory,
            prior_user_questions=prior_user_questions,
        )


_medical_service: MedicalChatService | None = None


def get_medical_service() -> MedicalChatService:
    global _medical_service
    if _medical_service is None:
        _medical_service = MedicalChatService()
    return _medical_service
