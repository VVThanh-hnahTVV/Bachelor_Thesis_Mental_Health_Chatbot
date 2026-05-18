"""Node: objection_detector — rule-based detection of user refusals / misunderstandings."""
from __future__ import annotations

from typing import Any, Literal

from app.wellness.suggestions import _user_refuses_breathing

ObjectionType = Literal["refusal", "misunderstanding", "repetition"] | None

_MISUNDERSTANDING = (
    "sai rồi",
    "hiểu sai",
    "không phải vậy",
    "that's not what",
    "not what i said",
    "you got it wrong",
    "bạn hiểu nhầm",
    "không đúng",
)

_REPETITION = (
    "lặp lại",
    "nói lại",
    "đã nói rồi",
    "you already said",
    "stop repeating",
    "đừng lặp",
    "same thing",
)

_REFUSAL = (
    "không muốn",
    "đừng bảo",
    "đừng nói",
    "stop telling",
    "i don't want",
    "leave me alone",
    "bỏ đi",
    "thôi đi",
    "đủ rồi",
)


def detect_objection(text: str) -> tuple[bool, ObjectionType]:
    """Return (detected, type) from user message."""
    t = text.lower().strip()
    if not t:
        return False, None
    if _user_refuses_breathing(text):
        return True, "refusal"
    if any(m in t for m in _MISUNDERSTANDING):
        return True, "misunderstanding"
    if any(m in t for m in _REPETITION):
        return True, "repetition"
    if any(m in t for m in _REFUSAL):
        return True, "refusal"
    return False, None


async def node_objection_detector(state: dict[str, Any]) -> dict[str, Any]:
    user_input: str = state.get("user_input", "")
    detected, obj_type = detect_objection(user_input)
    meta = dict(state.get("metadata") or {})
    if detected:
        meta["objection"] = True
        meta["objection_type"] = obj_type
    out: dict[str, Any] = {
        "objection_detected": detected,
        "objection_type": obj_type,
        "metadata": meta,
    }
    if detected:
        out["therapy_strategy"] = "reflective_listening"
    return out
