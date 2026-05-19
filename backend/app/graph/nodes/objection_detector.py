"""Node: objection_detector — LLM-based detection of user refusals / misunderstandings."""
from __future__ import annotations

import json
import logging
import re
from typing import Any, Literal

from langchain_core.messages import HumanMessage, SystemMessage

from app.config import ProviderName
from app.llm.factory import get_chat_model, invoke_with_fallback

logger = logging.getLogger(__name__)

ObjectionType = Literal["refusal", "misunderstanding", "repetition"] | None

VALID_OBJECTION_TYPES = frozenset({"refusal", "misunderstanding", "repetition"})

_SYSTEM = """\
You detect whether the user is objecting to Luna (the mental wellness companion) — not merely venting or asking what to do next.

Analyse the latest user message with recent conversation context. Return ONLY valid JSON:

{
  "objection_detected": <true|false>,
  "objection_type": "<type>" | null,
  "confidence": <0.0–1.0>
}

objection_type (only when objection_detected is true):
- refusal          : refuses a suggestion (breathing, grounding, exercise), says it does not help, wants Luna to stop advising
- misunderstanding : Luna got their meaning wrong ("you misunderstood", "that's not what I meant")
- repetition       : Luna keeps repeating the same thing, conversation feels circular, user is frustrated with Luna's approach

Set objection_detected: false when:
- User is venting, sad, hopeless, or sharing feelings without pushing back on Luna
- User asks a neutral follow-up after trying something ("what now?", "làm xong rồi sao nữa", "tiếp theo là gì") — they want progression, NOT an objection
- User says they don't know what to say but still want to talk
- Short replies like "chán" or "ok" without clearly blaming Luna's advice

Use recent assistant messages to judge repetition or misunderstanding — compare what Luna last said vs what upset the user.

No markdown, no prose — JSON only.
"""


def _parse_objection(raw: str) -> tuple[bool, ObjectionType, float]:
    m = re.search(r"\{[\s\S]*\}", raw)
    if not m:
        return False, None, 0.0
    try:
        data = json.loads(m.group())
    except json.JSONDecodeError:
        return False, None, 0.0

    detected = bool(data.get("objection_detected", False))
    confidence = float(data.get("confidence", 0.0))
    confidence = max(0.0, min(1.0, confidence))

    if not detected:
        return False, None, confidence

    raw_type = data.get("objection_type")
    if raw_type is None:
        return True, "refusal", confidence

    obj_type = str(raw_type).lower().strip()
    if obj_type not in VALID_OBJECTION_TYPES:
        obj_type = "refusal"

    return True, obj_type, confidence  # type: ignore[return-value]


async def classify_objection(
    user_input: str,
    history: list[dict[str, str]],
    provider: ProviderName,
    *,
    min_confidence: float = 0.55,
) -> tuple[bool, ObjectionType, float]:
    """LLM objection classifier. Returns (detected, type, confidence)."""
    text = (user_input or "").strip()
    if not text:
        return False, None, 0.0

    recent_ctx = "\n".join(
        f"{m.get('role', 'user')}: {m.get('content', '')}" for m in history[-8:]
    )
    human_content = (
        f"Recent context:\n{recent_ctx}\n\nLatest user message:\n{text}"
        if recent_ctx
        else text
    )

    try:
        llm = get_chat_model(provider)
        msg = await invoke_with_fallback(
            llm,
            [SystemMessage(content=_SYSTEM), HumanMessage(content=human_content)],
            primary=provider,
        )
        raw = msg.content if isinstance(msg.content, str) else str(msg.content)
        detected, obj_type, confidence = _parse_objection(raw)
        if detected and confidence < min_confidence:
            return False, None, confidence
        return detected, obj_type, confidence
    except Exception as exc:
        logger.warning("objection_detector LLM failed: %s", exc)
        return False, None, 0.0


async def node_objection_detector(state: dict[str, Any]) -> dict[str, Any]:
    user_input: str = state.get("user_input", "")
    history: list[dict[str, str]] = state.get("history", [])
    provider: ProviderName = state.get("provider", "openai")

    detected, obj_type, confidence = await classify_objection(
        user_input, history, provider
    )

    meta = dict(state.get("metadata") or {})
    if detected:
        meta["objection"] = True
        meta["objection_type"] = obj_type
        meta["objection_confidence"] = confidence

    out: dict[str, Any] = {
        "objection_detected": detected,
        "objection_type": obj_type,
        "metadata": meta,
    }
    if detected:
        out["therapy_strategy"] = "reflective_listening"
    return out
