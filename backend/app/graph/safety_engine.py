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
    "Mình rất lo lắng khi nghe điều bạn vừa chia sẻ. "
    "Bạn không đơn độc trong lúc này.\n\n"
    "**Nếu bạn đang trong nguy hiểm ngay lúc này, hãy gọi ngay:**\n"
    "- 🆘 **115** — Cấp cứu\n"
    "- 📞 **1800 599 920** — Đường dây hỗ trợ sức khỏe tâm thần (miễn phí, 24/7)\n\n"
    "Mình ở đây với bạn. Bạn có thể chọn một trong các bước nhỏ bên dưới để mình cùng đồng hành."
)

CRISIS_REPLY_EN = (
    "I'm really concerned by what you just shared. "
    "You do not have to go through this alone.\n\n"
    "**If you are in immediate danger right now, call your local emergency number now.**\n"
    "- In the United States or Canada: **988** — Suicide & Crisis Lifeline\n"
    "- If you are elsewhere: contact emergency services or a trusted person nearby immediately.\n\n"
    "I'm here with you. You can choose one small next step below."
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


_FALLBACK: SafetyResult = {
    "risk_level": "low",
    "confidence": 0.0,
    "triggers": [],
    "emergency_mode": False,
}

_CRISIS_KEYWORDS = (
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

_SUSPICIOUS_KEYWORDS = (
    "chết", "tự làm đau", "không còn lý do", "vô nghĩa", "cắt",
    "nhảy", "uống thuốc quá liều", "die", "kill", "hurt myself",
    "harm", "overdose", "hopeless", "end it",
)


def _keyword_risk(text: str) -> SafetyResult | None:
    low = text.lower()
    if any(kw in low for kw in _CRISIS_KEYWORDS):
        return SafetyResult(
            risk_level="high",
            confidence=0.98,
            triggers=["keyword_crisis"],
            emergency_mode=True,
        )
    if any(kw in low for kw in _SUSPICIOUS_KEYWORDS):
        return SafetyResult(
            risk_level="medium",
            confidence=0.75,
            triggers=["keyword_suspicious"],
            emergency_mode=False,
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
    return SafetyResult(
        risk_level=level,
        confidence=confidence,
        triggers=triggers,
        emergency_mode=(level == "high"),
    )


async def run_safety_engine(
    user_input: str,
    history: list[dict[str, str]],
    provider: ProviderName,
) -> SafetyResult:
    """Call LLM safety classifier. Always returns a SafetyResult."""
    # Fast keyword pre-screen to avoid LLM call on clearly safe messages
    keyword_result = _keyword_risk(user_input)
    if keyword_result and keyword_result["emergency_mode"]:
        return keyword_result
    _LOW_RISK_FAST = len(user_input) < 5 or keyword_result is None
    if _LOW_RISK_FAST:
        return SafetyResult(
            risk_level="low",
            confidence=0.95,
            triggers=[],
            emergency_mode=False,
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
        return _parse_safety_json(raw)
    except Exception as exc:
        if keyword_result:
            logger.warning("safety_engine LLM failed, using conservative keyword result: %s", exc)
            conservative = dict(keyword_result)
            conservative["triggers"] = [*conservative["triggers"], "llm_failure"]
            return conservative
        logger.warning("safety_engine LLM failed, defaulting to low: %s", exc)
        return dict(_FALLBACK)
