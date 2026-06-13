from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Literal

from langchain_core.messages import AIMessage
from pydantic import BaseModel, Field


class InputGuardrailOutput(BaseModel):
    status: Literal["SAFE", "UNSAFE"]
    reason: str = Field(
        default="",
        description="Brief explanation in English when UNSAFE; empty string when SAFE.",
    )
    user_language: str = Field(
        default="vi",
        description="Short language code for the user's message (e.g. vi, en, fr).",
    )
    needs_human: bool = Field(
        default=False,
        description="True when user explicitly or clearly wants human counselor support.",
    )
    handoff_confidence: float = Field(
        default=0.0,
        ge=0.0,
        le=1.0,
        description="Confidence 0-1 for needs_human when SAFE.",
    )
    handoff_reason: str = Field(
        default="",
        description="Brief English reason when needs_human is true.",
    )
    off_topic: bool = Field(
        default=False,
        description=(
            "True when the query is outside Helios scope (mental health / medical support) "
            "but not harmful — e.g. general trivia, homework, sports, unrelated coding."
        ),
    )


@dataclass(frozen=True)
class GuardrailInputResult:
    is_allowed: bool
    message: str | AIMessage
    user_language: str
    needs_human: bool = False
    handoff_confidence: float = 0.0
    is_off_topic: bool = False


DEFAULT_USER_LANGUAGE = "vi"

_VI_CHARS = re.compile(
    r"[àáạảãâầấậẩẫăằắặẳẵèéẹẻẽêềếệểễìíịỉĩòóọỏõôồốộổỗơờớợởỡùúụủũưừứựửữỳýỵỷỹđ]",
    re.IGNORECASE,
)
_VI_WORD_HINT = re.compile(
    r"\b(là|gì|của|cho|tôi|bạn|không|được|như|nào|xin|chào|vui|lòng|trị|liệu|tâm|lý)\b",
    re.IGNORECASE,
)
_EN_HINT = re.compile(
    r"\b(the|what|how|is|are|can|you|help|hello|hi|please|thanks|why|when|where|who|could|would)\b",
    re.IGNORECASE,
)


def has_clear_language_signal(text: str) -> bool:
    sample = text or ""
    return bool(
        _VI_CHARS.search(sample)
        or _VI_WORD_HINT.search(sample)
        or _EN_HINT.search(sample)
    )


def detect_user_language_fallback(
    text: str,
    *,
    default: str = DEFAULT_USER_LANGUAGE,
) -> str:
    """Heuristic when the guardrail model omits user_language."""
    sample = text or ""
    if _VI_CHARS.search(sample) or _VI_WORD_HINT.search(sample):
        return "vi"
    if _EN_HINT.search(sample):
        return "en"
    return default


def resolve_user_language(
    text: str,
    *,
    prior_user_messages: list[str] | None = None,
    default: str = DEFAULT_USER_LANGUAGE,
) -> str:
    """Pick response language; use conversation history when the current turn is ambiguous."""
    if has_clear_language_signal(text):
        return detect_user_language_fallback(text, default=default)
    for prior in reversed(prior_user_messages or []):
        prior_text = (prior or "").strip()
        if prior_text and has_clear_language_signal(prior_text):
            return detect_user_language_fallback(prior_text, default=default)
    return default


def normalize_language_code(code: str, *, default: str = DEFAULT_USER_LANGUAGE) -> str:
    cleaned = (code or "").strip().lower().replace("_", "-")
    if not cleaned:
        return default
    return cleaned.split("-", 1)[0]


_MEDICAL_SCOPE = re.compile(
    r"(tâm\s*lý|tâm\s*thần|mental\s*health|sức\s*khỏe|wellness|well-being|"
    r"stress|lo\s*âu|anxiety|depression|trầm\s*cảm|therapy|trị\s*liệu|"
    r"symptom|triệu\s*chứng|chẩn\s*đoán|diagnos|burnout|căng\s*thẳng|"
    r"PTSD|CBT|OCD|bipolar|psychiatr|psycholog|mood|emotion|cảm\s*xúc|"
    r"insomnia|mất\s*ngủ|suicide|tự\s*tử|self-harm|counsel|tư\s*vấn|"
    r"medical|y\s*tế|bệnh|disease|treatment|điều\s*trị|thuốc|medicine|"
    r"Helios|handoff|chuyên\s*viên|counselor)",
    re.IGNORECASE,
)
_META_FOLLOWUP = re.compile(
    r"(nguồn|source|reference|tham\s*khảo|where\s+did\s+you|lấy\s+thông\s+tin|"
    r"bạn\s+biết\s+từ\s+đâu|tin\s+cậy|trust|why\s+did\s+you\s+say)",
    re.IGNORECASE,
)
_GREETING_OR_SCOPE = re.compile(
    r"^(chào|hello|hi|hey|xin\s+chào)\b|"
    r"(bạn\s+có\s+thể\s+giúp|what\s+can\s+you\s+help|bạn\s+là\s+ai|who\s+are\s+you)",
    re.IGNORECASE,
)
_OFF_TOPIC_TRIVIA = re.compile(
    r"(\bquốc\s*gia\b|\bcountries\b|\bcountry\s+count\b|bao\s+nhiêu\s+nước|"
    r"\bthủ\s*đô\b|\bcapital\s+of\b|\bdân\s*số\b|\bpopulation\s+of\b|"
    r"\bai\s+(đặt|invented|sáng\s+chế)\b|\bwho\s+invented\b|\bnăm\s+nào\b|"
    r"\bwhat\s+year\b|\btỉ\s*số\b|\bworld\s+cup\b|\bbóng\s*đá\b|"
    r"\bdịch\s+(hộ|giúp)\b|\btranslate\b|\bviết\s+code\b|\bwrite\s+code\b|"
    r"\bdebug\b|\bhomework\b|\bbài\s+tập\b|\btính\s+toán\b|\bcalculate\b|"
    r"\bgiá\s+vàng\b|\bstock\s+price\b|\bthời\s+tiết\b|\bweather\b)",
    re.IGNORECASE,
)


def has_medical_conversation_context(
    *,
    conversation_summary: str = "",
    recent_user_questions: str = "",
) -> bool:
    blob = f"{conversation_summary}\n{recent_user_questions}"
    return bool(_MEDICAL_SCOPE.search(blob))


def looks_like_off_topic_heuristic(
    text: str,
    *,
    conversation_summary: str = "",
    recent_user_questions: str = "",
) -> bool:
    """Fast path: block obvious general-knowledge trivia outside Helios scope."""
    sample = (text or "").strip()
    if not sample:
        return False
    if _GREETING_OR_SCOPE.search(sample):
        return False
    if _MEDICAL_SCOPE.search(sample):
        return False
    if has_medical_conversation_context(
        conversation_summary=conversation_summary,
        recent_user_questions=recent_user_questions,
    ) and _META_FOLLOWUP.search(sample):
        return False
    return bool(_OFF_TOPIC_TRIVIA.search(sample))
