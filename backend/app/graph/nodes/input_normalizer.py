"""Node 1: input_normalize — lightweight, no LLM."""
from __future__ import annotations

import re
from typing import Any


_VI_PATTERN = re.compile(
    r"[àáâãèéêìíòóôõùúýăđơưạảấầẩẫậắằẳẵặẹẻẽếềểễệỉịọỏốồổỗộớờởỡợụủứừửữựỳỷỹỵ]",
    re.IGNORECASE,
)


def _detect_language(text: str) -> str:
    """Heuristic: if text contains Vietnamese diacritics → 'vi', else 'en'."""
    return "vi" if _VI_PATTERN.search(text) else "en"


def node_input_normalize(state: dict[str, Any]) -> dict[str, Any]:
    raw: str = state.get("user_input", "")
    cleaned = raw.strip()
    language = _detect_language(cleaned)
    meta = dict(state.get("metadata") or {})
    meta["language"] = language
    return {"user_input": cleaned, "language": language, "metadata": meta}
