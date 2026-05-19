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

_NEXT_STEP_FALLBACK_VI = (
    "Cảm ơn bạn đã thử bước nhỏ đó. "
    "Điều gì đang nặng nhất với bạn ngay lúc này — cảm xúc hay chuyện với người bạn quan tâm?"
)
_NEXT_STEP_FALLBACK_EN = (
    "Thank you for trying that small step. "
    "What feels heaviest for you right now — the feeling itself or something about the person you care about?"
)

_FOLLOWUP_MARKERS = (
    "rồi sao",
    "xong rồi",
    "làm xong",
    "tiếp theo",
    "sau đó",
    "what now",
    "what next",
    "done now",
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

_REWRITE_SYSTEM = """\
You rewrite a mental-health companion reply that failed a safety review.
Rules:
- Keep the SAME language as the user.
- Preserve empathy and references to what the user actually shared in the conversation.
- Remove ONLY the unsafe parts; do not replace the whole message with a generic script.
- Goal: help the user feel heard and heal — stay on their story (breakup, grief, etc.).
- Do NOT use vague lines like "dealing with something tough" or "share a bit more" without context.
- Output only the rewritten reply, no labels.
"""


def _is_followup_question(user_input: str) -> bool:
    t = user_input.lower().strip()
    return any(m in t for m in _FOLLOWUP_MARKERS)


def _safe_fallback(state: dict[str, Any]) -> str:
    history: list[dict[str, str]] = state.get("history") or []
    user_input = state.get("user_input", "")
    lang = detect_language(user_input, history)
    if _is_followup_question(user_input):
        return _NEXT_STEP_FALLBACK_VI if lang == "vi" else _NEXT_STEP_FALLBACK_EN
    return _SAFE_FALLBACK_VI if lang == "vi" else _SAFE_FALLBACK_EN


def _history_text(history: list[dict[str, str]], max_turns: int = 8) -> str:
    return "\n".join(
        f"{t.get('role', 'user')}: {t.get('content', '')}"
        for t in history[-max_turns:]
    )


async def _rewrite_unsafe_reply(
    state: dict[str, Any],
    reply: str,
    issues: list[Any],
    *,
    provider: ProviderName,
) -> str:
    user_input = state.get("user_input", "")
    history: list[dict[str, str]] = state.get("history") or []
    hist = _history_text(history)
    human = (
        f"Issues flagged: {', '.join(str(i) for i in issues) or 'unspecified'}\n\n"
        f"Recent conversation:\n{hist or '(none)'}\n\n"
        f"Latest user message:\n{user_input}\n\n"
        f"Reply to rewrite:\n{reply}"
    )
    try:
        llm = get_chat_model(provider)
        msg = await invoke_with_fallback(
            llm,
            [SystemMessage(content=_REWRITE_SYSTEM), HumanMessage(content=human)],
            primary=provider,
        )
        text = msg.content if isinstance(msg.content, str) else str(msg.content)
        rewritten = text.strip()
        if len(rewritten) >= 40:
            return rewritten
    except Exception as exc:
        logger.warning("response_filter rewrite failed: %s", exc)
    return _safe_fallback(state)


async def node_response_filter(state: dict[str, Any]) -> dict[str, Any]:
    reply: str = state.get("final_reply", "")
    provider: ProviderName = state.get("provider", "openai")
    fallback = _safe_fallback(state)

    if not reply.strip():
        return {"final_reply": fallback, "response_safe": False}

    issues: list[Any] = []
    safe = True
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
        rewritten = await _rewrite_unsafe_reply(
            state, reply, issues, provider=provider
        )
        return {"final_reply": rewritten, "response_safe": False}

    return {"response_safe": True}
