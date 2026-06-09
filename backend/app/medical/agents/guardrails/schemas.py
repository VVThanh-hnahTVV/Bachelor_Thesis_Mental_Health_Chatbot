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


@dataclass(frozen=True)
class GuardrailInputResult:
    is_allowed: bool
    message: str | AIMessage
    user_language: str


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
