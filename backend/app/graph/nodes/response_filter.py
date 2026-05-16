"""Node 6: response_filter — post-generation safety check."""
from __future__ import annotations

import json
import logging
import re
from typing import Any

from langchain_core.messages import HumanMessage, SystemMessage

from app.config import ProviderName
from app.graph.nodes.response_generator import detect_language
from app.llm.factory import get_chat_model, invoke_with_fallback

logger = logging.getLogger(__name__)

_SAFE_FALLBACK_VI = (
    "Mình nghe thấy bạn đang trải qua điều gì đó khó khăn. "
    "Bạn có muốn chia sẻ thêm một chút để mình hiểu rõ hơn không?"
)
_SAFE_FALLBACK_EN = (
    "I hear that you're going through something difficult. "
    "Would you like to share a bit more so I can better understand?"
)

_SYSTEM = """\
You are a response safety auditor for a mental health chatbot.
Review the assistant's reply for ANY of these issues:
- harmful_advice     : advice that could worsen mental health or cause harm
- medical_claim      : claims about diagnoses, medications, or treatments without qualification
- dependency_language: phrases that make the user dependent on the chatbot ("only I understand you", etc.)
- manipulation       : emotional manipulation or guilt-tripping
- dismissive         : minimising or invalidating the user's feelings

Reply ONLY with valid JSON:
{"safe": true, "issues": []}
or
{"safe": false, "issues": ["<issue_type>", ...]}
"""


def _safe_fallback(state: dict[str, Any]) -> str:
    history: list[dict[str, str]] = state.get("history") or []
    lang = detect_language(state.get("user_input", ""), history)
    return _SAFE_FALLBACK_VI if lang == "vi" else _SAFE_FALLBACK_EN


async def node_response_filter(state: dict[str, Any]) -> dict[str, Any]:
    reply: str = state.get("final_reply", "")
    provider: ProviderName = state.get("provider", "openai")
    fallback = _safe_fallback(state)

    if not reply.strip():
        return {"final_reply": fallback, "response_safe": False}

    try:
        llm = get_chat_model(provider)
        msg = await invoke_with_fallback(
            llm,
            [
                SystemMessage(content=_SYSTEM),
                HumanMessage(content=f"Assistant reply to check:\n{reply}"),
            ],
            primary=provider,
        )
        raw = msg.content if isinstance(msg.content, str) else str(msg.content)
        m = re.search(r"\{[^{}]+\}", raw, re.DOTALL)
        safe = True
        if m:
            try:
                data = json.loads(m.group())
                safe = bool(data.get("safe", True))
                if not safe:
                    issues = data.get("issues", [])
                    logger.warning("response_filter flagged reply: %s", issues)
            except json.JSONDecodeError:
                pass
    except Exception as exc:
        logger.warning("response_filter LLM failed (pass-through): %s", exc)
        safe = True

    if not safe:
        return {"final_reply": fallback, "response_safe": False}
    return {"response_safe": True}
