"""Structured JSON fields returned by routing, conversation, RAG, and web-search agents."""

from __future__ import annotations

import logging
import re
from typing import Any

from langchain_core.output_parsers import JsonOutputParser
from pydantic import BaseModel, Field

logger = logging.getLogger(__name__)

SUGGEST_ACTIVITIES_RULES = """\
### suggest_activities
Set to true ONLY when the user message shows they want help with emotional distress, relaxation, or calming down
(e.g. lo âu, căng thẳng, mất ngủ, stress, overwhelmed, cần thư giãn, hít thở, mindfulness for mood).
Set to false for purely informational medical questions (disease mechanisms, treatment options, medication names,
symptom lists, "làm sao để giảm X" as medical management) unless they also express distress or ask for exercises.
Examples:
- "Sao để giảm ADHD" -> suggest_activities: false
- "Tôi lo âu mất ngủ, có bài tập nào không" -> suggest_activities: true
- "Thuốc methylphenidate tác dụng phụ gì" -> suggest_activities: false
"""

ACTIVITIES_INTRO_RULES = """\
### activities_intro
When suggest_activities is true, write 1–2 short warm sentences in **English** (internal draft) that bridge from your
medical answer to the exercise buttons shown **below** this message. Invite the user to tap **Open** on a button to
start a guided in-app exercise. Do not name specific exercise titles (buttons already show them). Keep activities_intro
separate from "answer" — the system appends it after the answer. Final localization to the user's language happens later.
When suggest_activities is false, set activities_intro to "".
Example (insomnia): "Besides the habits above, you can try a short relaxation exercise in the app — tap **Open** below to start."
"""


class RouteAgentDecision(BaseModel):
    agent: str = Field(
        description=(
            "One of CONVERSATION_AGENT, RAG_AGENT, or WEB_SEARCH_PROCESSOR_AGENT."
        )
    )
    reasoning: str = Field(description="Step-by-step reasoning for the routing choice.")
    confidence: float = Field(
        ge=0.0,
        le=1.0,
        description="Confidence in the routing decision.",
    )
    sub_queries: list[str] = Field(
        default_factory=list,
        description=(
            "When agent is RAG_AGENT: 1-4 retrieval sub-queries per distinct information need, "
            "in English and in any other language indicated by lang= on matched ingested sources "
            "(e.g. Vietnamese when lang=vi). Empty for other agents."
        ),
    )


class ConversationAgentOutput(BaseModel):
    answer: str = Field(
        description="User-facing conversational reply in markdown."
    )
    suggest_activities: bool = Field(
        description="True when in-app wellness/relaxation exercise buttons should be shown."
    )
    activities_intro: str = Field(
        default="",
        description="Bridge text inviting user to open in-app exercises below; empty when suggest_activities is false.",
    )


class RAGAgentOutput(BaseModel):
    answer: str = Field(
        description="User-facing answer in markdown, based only on the provided context."
    )
    web_search: bool = Field(
        description=(
            "True when the retrieved context cannot fully answer the user's question "
            "and a broader web search would help."
        )
    )
    suggest_activities: bool = Field(
        description="True when wellness/relaxation activities would genuinely help the user."
    )
    activities_intro: str = Field(
        default="",
        description="Bridge text inviting user to open in-app exercises below; empty when suggest_activities is false.",
    )


class WebSearchAgentOutput(BaseModel):
    answer: str = Field(description="User-facing answer in markdown from search results.")
    suggest_activities: bool = Field(
        description="True when wellness/relaxation activities would genuinely help the user."
    )
    activities_intro: str = Field(
        default="",
        description="Bridge text inviting user to open in-app exercises below; empty when suggest_activities is false.",
    )


_rag_parser = JsonOutputParser(pydantic_object=RAGAgentOutput)
_web_parser = JsonOutputParser(pydantic_object=WebSearchAgentOutput)
_conversation_parser = JsonOutputParser(pydantic_object=ConversationAgentOutput)


def rag_format_instructions() -> str:
    return _rag_parser.get_format_instructions()


def web_search_format_instructions() -> str:
    return _web_parser.get_format_instructions()


def conversation_format_instructions() -> str:
    return _conversation_parser.get_format_instructions()


def merge_activities_intro(
    answer: str,
    *,
    suggest_activities: bool,
    activities_intro: str,
) -> str:
    """Append activities_intro to answer when wellness buttons will be shown."""
    base = (answer or "").strip()
    intro = (activities_intro or "").strip()
    if not suggest_activities or not intro:
        return base
    if not base:
        return intro
    return f"{base}\n\n{intro}"


def _strip_json_fence(text: str) -> str:
    stripped = text.strip()
    if stripped.startswith("```"):
        stripped = re.sub(r"^```(?:json)?\s*", "", stripped)
        stripped = re.sub(r"\s*```$", "", stripped)
    return stripped.strip()


def parse_rag_output(raw: Any) -> RAGAgentOutput:
    text = raw.content if hasattr(raw, "content") else str(raw)
    try:
        data = _rag_parser.parse(_strip_json_fence(str(text)))
        return RAGAgentOutput.model_validate(data)
    except Exception as exc:  # noqa: BLE001
        logger.warning("RAG JSON parse failed, using fallback: %s", exc)
        body = str(text).strip()
        return RAGAgentOutput(
            answer=body or "I could not generate a response.",
            web_search=_fallback_web_search_flag(body),
            suggest_activities=False,
            activities_intro="",
        )


def parse_conversation_output(raw: Any) -> ConversationAgentOutput:
    text = raw.content if hasattr(raw, "content") else str(raw)
    try:
        data = _conversation_parser.parse(_strip_json_fence(str(text)))
        return ConversationAgentOutput.model_validate(data)
    except Exception as exc:  # noqa: BLE001
        logger.warning("Conversation JSON parse failed, using fallback: %s", exc)
        body = str(text).strip()
        if "Conversational LLM Response:" in body:
            body = body.split("Conversational LLM Response:", 1)[-1].strip()
        return ConversationAgentOutput(
            answer=body or "I could not generate a response.",
            suggest_activities=False,
            activities_intro="",
        )


def parse_web_search_output(raw: Any) -> WebSearchAgentOutput:
    text = raw.content if hasattr(raw, "content") else str(raw)
    try:
        data = _web_parser.parse(_strip_json_fence(str(text)))
        return WebSearchAgentOutput.model_validate(data)
    except Exception as exc:  # noqa: BLE001
        logger.warning("Web search JSON parse failed, using fallback: %s", exc)
        body = str(text).strip()
        return WebSearchAgentOutput(
            answer=body or "I could not generate a response.",
            suggest_activities=False,
            activities_intro="",
        )


def _fallback_web_search_flag(answer: str) -> bool:
    lower = answer.lower()
    markers = (
        "don't have enough information",
        "do not have enough information",
        "not enough information",
        "insufficient information",
        "cannot answer",
        "unable to answer",
        "không có đủ thông tin",
        "không đủ thông tin",
        "không thể trả lời",
    )
    return any(m in lower for m in markers)
