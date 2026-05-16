"""Node 2: emotion_intent — single LLM call for emotion + intent classification."""
from __future__ import annotations

import json
import logging
import re
from typing import Any

from langchain_core.messages import HumanMessage, SystemMessage

from app.config import ProviderName
from app.llm.factory import get_chat_model, invoke_with_fallback

logger = logging.getLogger(__name__)

VALID_INTENTS = frozenset({
    "venting",
    "seeking_advice",
    "panic_support",
    "off_topic",
    "casual",
    "journaling",
    "loneliness",
    "sleep_issues",
    "relationship_stress",
    "general_health",
})

VALID_EMOTIONS = frozenset({
    "anxiety", "sadness", "anger", "hopeless",
    "neutral", "overwhelmed", "lonely", "grief",
    "fear", "shame", "guilt", "joy",
})

_SYSTEM = """\
You are an empathy classifier for a mental health support app.
Analyse the user's latest message (with recent context) and return ONLY valid JSON:

{
  "primary_emotion": "<emotion>",
  "emotion_intensity": <0.0–1.0>,
  "intent": "<intent>"
}

emotion options: anxiety, sadness, anger, hopeless, neutral, overwhelmed, lonely, grief, fear, shame, guilt, joy
intent options:
  - casual           : greetings, small talk, asking who Luna is or what Luna can help with
                       ("xin chào", "bạn là ai", "bạn có thể giúp gì", "hello", "what can you do")
  - venting          : expressing feelings without asking for advice
  - seeking_advice   : explicitly wants guidance or solutions
  - panic_support    : in acute distress / panic
  - journaling       : reflecting on events / self-exploration
  - loneliness       : feeling isolated or disconnected
  - sleep_issues     : problems with sleep
  - relationship_stress : relationship difficulties (family, romantic, work)
  - general_health   : general physical or mental health question
  - off_topic        : clearly unrelated to health, emotions, or wellbeing (e.g. maths problems, coding, cooking recipes)

Priority rules:
- Greetings and pleasantries → ALWAYS "casual", never "off_topic"
- Questions touching feelings, body, mind, relationships, stress → health-related intents, never "off_topic"
- Reserve "off_topic" ONLY for requests that have nothing to do with wellbeing whatsoever.
No markdown, no prose — JSON only.
"""


def _parse(raw: str) -> tuple[str, float, str]:
    m = re.search(r"\{[^{}]+\}", raw, re.DOTALL)
    if not m:
        return "neutral", 0.5, "general_health"
    try:
        data = json.loads(m.group())
    except json.JSONDecodeError:
        return "neutral", 0.5, "general_health"

    emotion = str(data.get("primary_emotion", "neutral")).lower()
    if emotion not in VALID_EMOTIONS:
        emotion = "neutral"

    intensity = float(data.get("emotion_intensity", 0.5))
    intensity = max(0.0, min(1.0, intensity))

    intent = str(data.get("intent", "general_health")).lower()
    if intent not in VALID_INTENTS:
        intent = "general_health"

    return emotion, intensity, intent


async def node_emotion_intent(state: dict[str, Any]) -> dict[str, Any]:
    user_input: str = state.get("user_input", "")
    history: list[dict[str, str]] = state.get("history", [])
    provider: ProviderName = state.get("provider", "openai")

    recent_ctx = "\n".join(
        f"{m['role']}: {m['content']}" for m in history[-6:]
    )
    human_content = (
        f"Recent context:\n{recent_ctx}\n\nLatest message:\n{user_input}"
        if recent_ctx
        else user_input
    )

    try:
        llm = get_chat_model(provider)
        msg = await invoke_with_fallback(
            llm,
            [SystemMessage(content=_SYSTEM), HumanMessage(content=human_content)],
            primary=provider,
        )
        raw = msg.content if isinstance(msg.content, str) else str(msg.content)
        emotion, intensity, intent = _parse(raw)
    except Exception as exc:
        logger.warning("emotion_intent node failed: %s", exc)
        emotion, intensity, intent = "neutral", 0.5, "general_health"

    meta = dict(state.get("metadata") or {})
    meta["emotion_raw"] = f"{emotion}@{intensity:.2f}"
    return {
        "primary_emotion": emotion,
        "emotion_intensity": intensity,
        "intent": intent,
        "metadata": meta,
    }
