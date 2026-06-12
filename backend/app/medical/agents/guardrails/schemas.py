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
        default="en",
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


@dataclass(frozen=True)
class GuardrailInputResult:
    is_allowed: bool
    message: str | AIMessage
    user_language: str
    needs_human: bool = False
    handoff_confidence: float = 0.0


_VI_CHARS = re.compile(
    r"[àáạảãâầấậẩẫăằắặẳẵèéẹẻẽêềếệểễìíịỉĩòóọỏõôồốộổỗơờớợởỡùúụủũưừứựửữỳýỵỷỹđ]",
    re.IGNORECASE,
)


def detect_user_language_fallback(text: str) -> str:
    """Heuristic when the guardrail model omits user_language."""
    if _VI_CHARS.search(text or ""):
        return "vi"
    return "en"


def normalize_language_code(code: str) -> str:
    cleaned = (code or "").strip().lower().replace("_", "-")
    if not cleaned:
        return "en"
    return cleaned.split("-", 1)[0]
