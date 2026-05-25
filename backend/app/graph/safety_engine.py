"""Standalone parallel safety engine.

Runs concurrently with the main LangGraph pipeline via asyncio.create_task.
Never raises — always returns a SafetyResult even on LLM failure.
"""
from __future__ import annotations

import json
import logging
import re
from typing import Any, TypedDict

from langchain_core.messages import HumanMessage, SystemMessage

from app.config import ProviderName
from app.llm.factory import get_chat_model, invoke_with_fallback

logger = logging.getLogger(__name__)

CRISIS_CHOICES_VI = [
    "Tôi muốn thử bài tập hít thở",
    "Cho tôi nghe âm sóng thư giãn",
    "Tôi muốn xem số điện thoại hỗ trợ",
    "Tôi cảm thấy đỡ hơn một chút rồi",
]

CRISIS_CHOICES_EN = [
    "I want to try a breathing exercise",
    "Play calming ocean sounds",
    "Show me support numbers",
    "I feel a little safer now",
]

CRISIS_REPLY_VI = (
    "Bạn xứng đáng được sống, dù lúc này có thể bạn không cảm thấy như vậy.\n\n"
    "Là một AI, mình không phải người phù hợp nhất để đồng hành với bạn trong khoảnh khắc này — "
    "bạn xứng đáng được nhận sự hỗ trợ từ một con người thực sự.\n\n"
    "**Hãy liên hệ với một trong những đường dây dưới đây ngay bây giờ:**\n"
    "- 📞 **1800 599 920** — Sức khỏe tâm thần (miễn phí, 24/7)\n"
    "- 🆘 **115** — Cấp cứu\n"
    "- 📞 **1800 599 920** — Đường dây hỗ trợ tâm lý học đường\n\n"
    "Mình ở đây với bạn. Bạn có thể chọn một bước nhỏ bên dưới trong khi chờ đợi."
)

CRISIS_REPLY_EN = (
    "You are worth your life, even if it might not feel that way to you right now.\n\n"
    "As a bot, I'm not best suited to provide the support you deserve in this moment — "
    "you deserve to speak with a real person who is trained to help.\n\n"
    "**Please reach out to one of these right now:**\n"
    "- 🇺🇸/🇨🇦 **988** — Suicide & Crisis Lifeline (call or text, 24/7)\n"
    "- 🌍 **findahelpline.com** — Find a crisis line anywhere in the world\n"
    "- 🆘 **Emergency services** — Call your local emergency number if you are in immediate danger\n\n"
    "I'm here with you. You can choose one small next step below while you reach out."
)


def crisis_reply_for_language(lang: str) -> tuple[str, list[str]]:
    if lang == "en":
        return CRISIS_REPLY_EN, CRISIS_CHOICES_EN
    return CRISIS_REPLY_VI, CRISIS_CHOICES_VI

_SAFETY_SYSTEM = """\
You are a mental-health safety classifier. Analyse the user message for crisis signals.

Detect ANY of:
- explicit or implicit suicide / self-harm intent ("tôi muốn chết", "không muốn sống", "I want to die", etc.)
- self-harm plans or descriptions
- severe hopelessness ("không còn lý do gì để tiếp tục", "mọi thứ đều vô nghĩa", etc.)
- eating-disorder crisis
- abuse / violence (being harmed or harming others)
- severe panic / psychosis cues

Respond with ONLY valid JSON — no markdown, no prose:
{
  "risk_level": "low" | "medium" | "high",
  "confidence": <0.0–1.0>,
  "triggers": ["<tag>", ...]
}

risk_level rules:
- "high"   : explicit intent, imminent plan, or immediate danger
- "medium" : strong warning signs but no explicit plan
- "low"    : no crisis signals
"""


class SafetyResult(TypedDict):
    risk_level: str       # "low" | "medium" | "high"
    confidence: float
    triggers: list[str]
    emergency_mode: bool
    suggested_stage: str  # "none" | "concern" | "confirm" | "sos"


_FALLBACK: SafetyResult = {
    "risk_level": "low",
    "confidence": 0.0,
    "triggers": [],
    "emergency_mode": False,
    "suggested_stage": "none",
}

_EXPLICIT_CRISIS_KEYWORDS = (
    "tôi muốn chết",
    "muốn chết",
    "tự tử",
    "không muốn sống",
    "i want to die",
    "want to die",
    "kill myself",
    "suicide",
    "end my life",
)

_IMMINENT_KEYWORDS = (
    "tối nay",
    "ngay bây giờ",
    "right now",
    "tonight",
    "đã uống thuốc",
    "đã cắt",
    "already took",
    "overdose now",
    "going to kill",
    "sẽ tự tử",
    "will kill myself",
    "have a plan",
    "có kế hoạch",
)

_SUSPICIOUS_KEYWORDS = (
    "chết", "tự làm đau", "không còn lý do", "vô nghĩa", "cắt",
    "nhảy", "uống thuốc quá liều", "die", "kill", "hurt myself",
    "harm", "overdose", "hopeless", "end it",
)


def _make_result(
    *,
    risk_level: str,
    confidence: float,
    triggers: list[str],
    emergency_mode: bool,
    suggested_stage: str,
) -> SafetyResult:
    return SafetyResult(
        risk_level=risk_level,
        confidence=confidence,
        triggers=triggers,
        emergency_mode=emergency_mode,
        suggested_stage=suggested_stage,
    )


def _keyword_risk(text: str) -> SafetyResult | None:
    low = text.lower()
    if any(kw in low for kw in _IMMINENT_KEYWORDS):
        return _make_result(
            risk_level="high",
            confidence=0.99,
            triggers=["keyword_imminent"],
            emergency_mode=True,
            suggested_stage="sos",
        )
    if any(kw in low for kw in _EXPLICIT_CRISIS_KEYWORDS):
        return _make_result(
            risk_level="high",
            confidence=0.98,
            triggers=["keyword_crisis"],
            emergency_mode=False,
            suggested_stage="concern",
        )
    if any(kw in low for kw in _SUSPICIOUS_KEYWORDS):
        return _make_result(
            risk_level="medium",
            confidence=0.75,
            triggers=["keyword_suspicious"],
            emergency_mode=False,
            suggested_stage="concern",
        )
    return None


def _parse_safety_json(raw: str) -> SafetyResult:
    m = re.search(r"\{[^{}]+\}", raw, re.DOTALL)
    if not m:
        return dict(_FALLBACK)
    try:
        data: dict[str, Any] = json.loads(m.group())
    except json.JSONDecodeError:
        return dict(_FALLBACK)

    level = str(data.get("risk_level", "low")).lower()
    if level not in ("low", "medium", "high"):
        level = "low"
    confidence = float(data.get("confidence", 0.0))
    triggers: list[str] = [str(t) for t in data.get("triggers", [])]

    if level == "high":
        imminent = any(
            t in triggers
            for t in ("imminent", "plan", "immediate", "overdose", "self_harm_plan")
        )
        if imminent:
            return _make_result(
                risk_level="high",
                confidence=confidence,
                triggers=triggers,
                emergency_mode=True,
                suggested_stage="sos",
            )
        return _make_result(
            risk_level="high",
            confidence=confidence,
            triggers=triggers,
            emergency_mode=False,
            suggested_stage="concern",
        )
    if level == "medium":
        return _make_result(
            risk_level="medium",
            confidence=confidence,
            triggers=triggers,
            emergency_mode=False,
            suggested_stage="concern",
        )
    return _make_result(
        risk_level="low",
        confidence=confidence,
        triggers=triggers,
        emergency_mode=False,
        suggested_stage="none",
    )


async def run_safety_engine(
    user_input: str,
    history: list[dict[str, str]],
    provider: ProviderName,
) -> SafetyResult:
    """Call LLM safety classifier. Always returns a SafetyResult."""
    keyword_result = _keyword_risk(user_input)
    if keyword_result and keyword_result["emergency_mode"]:
        return keyword_result
    _LOW_RISK_FAST = len(user_input) < 5 or keyword_result is None
    if _LOW_RISK_FAST:
        return _make_result(
            risk_level="low",
            confidence=0.95,
            triggers=[],
            emergency_mode=False,
            suggested_stage="none",
        )

    try:
        llm = get_chat_model(provider)
        recent_ctx = "\n".join(
            f"{m['role']}: {m['content']}" for m in history[-6:]
        )
        human_content = (
            f"Recent context:\n{recent_ctx}\n\nLatest message:\n{user_input}"
            if recent_ctx
            else user_input
        )
        msg = await invoke_with_fallback(
            llm,
            [SystemMessage(content=_SAFETY_SYSTEM), HumanMessage(content=human_content)],
            primary=provider,
        )
        raw = msg.content if isinstance(msg.content, str) else str(msg.content)
        parsed = _parse_safety_json(raw)
        if keyword_result and parsed["risk_level"] == "low":
            return keyword_result
        return parsed
    except Exception as exc:
        if keyword_result:
            logger.warning("safety_engine LLM failed, using conservative keyword result: %s", exc)
            conservative = dict(keyword_result)
            conservative["triggers"] = [*conservative["triggers"], "llm_failure"]
            return conservative
        logger.warning("safety_engine LLM failed, defaulting to low: %s", exc)
        return dict(_FALLBACK)
