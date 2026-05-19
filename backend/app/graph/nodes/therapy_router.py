"""Node 4: therapy_router — select therapeutic strategy based on emotion + intent."""
from __future__ import annotations

import json
import logging
import re
from typing import Any

from langchain_core.messages import HumanMessage, SystemMessage

from app.config import ProviderName
from app.graph.nodes.response_generator import is_meta_conversation
from app.llm.factory import get_chat_model, invoke_with_fallback

logger = logging.getLogger(__name__)

VALID_STRATEGIES = frozenset({
    "CBT",
    "grounding",
    "reflective_listening",
    "behavioral_activation",
    "psychoeducation",
    "stabilization",
})

_RELATIONSHIP_KEYWORDS = (
    "yêu",
    "thích",
    "crush",
    "người yêu",
    "không yêu",
    "từ chối",
    "bỏ rơi",
    "chia tay",
    "unrequited",
    "rejected",
    "breakup",
    "relationship",
    "tình cảm",
)

_POST_STABILIZATION_USER_MARKERS = (
    "rồi sao",
    "xong rồi",
    "làm xong",
    "tiếp theo",
    "sau đó",
    "what now",
    "what next",
    "done now",
    "chán",
    "không giúp",
    "vô ích",
    "vòng vo",
)

# Rule-based fast-path (avoids LLM call for clear cases)
_FAST_PATH: list[tuple[set[str], set[str], str]] = [
    (set(), {"casual"}, "reflective_listening"),
    ({"anxiety", "overwhelmed", "fear"}, {"panic_support"}, "grounding"),
    ({"lonely", "grief", "sadness"}, {"venting", "loneliness"}, "reflective_listening"),
    (set(), {"sleep_issues"}, "psychoeducation"),
    (set(), {"journaling"}, "reflective_listening"),
    (set(), {"relationship_stress"}, "reflective_listening"),
]

_SYSTEM = """\
You are a clinical decision support tool. Choose the most appropriate therapeutic strategy
for the user based on their emotion, intent, and context.

Available strategies:
- CBT                  : cognitive reframing, identifying distortions — for anxiety, overthinking, self-criticism
- grounding            : 5-4-3-2-1 sensory anchoring or breathing — for acute panic/overwhelm
- reflective_listening : validate and reflect feelings without advice — for venting, grief, loneliness
- behavioral_activation: schedule small pleasant activities — for low mood, motivation issues
- psychoeducation      : provide evidence-based information — for sleep, nutrition, general questions
- stabilization        : grounding without analysis or reframe — for trauma hints, severe distress

Reply ONLY with valid JSON: {"strategy": "<strategy>"}
"""


def _user_blob(state: dict[str, Any]) -> str:
    history: list[dict[str, str]] = state.get("history") or []
    user_lines = [m.get("content", "") for m in history if m.get("role") == "user"][-3:]
    return " ".join(user_lines + [state.get("user_input", "")]).lower()


def has_relationship_context(state: dict[str, Any]) -> bool:
    blob = _user_blob(state)
    return any(kw in blob for kw in _RELATIONSHIP_KEYWORDS)


def is_post_stabilization_followup(user_input: str) -> bool:
    t = user_input.lower().strip()
    return any(m in t for m in _POST_STABILIZATION_USER_MARKERS)


def resolve_hopeless_strategy(state: dict[str, Any]) -> str:
    """First hopeless turn → stabilization; later → post_stabilization or CBT."""
    flags: dict[str, Any] = state.get("therapy_flags") or {}
    user_input: str = state.get("user_input", "")
    if flags.get("stabilization_turn") and (
        is_post_stabilization_followup(user_input)
        or flags.get("last_strategy") == "stabilization"
    ):
        if has_relationship_context(state):
            return "post_stabilization"
        return "CBT"
    if not flags.get("stabilization_turn"):
        return "stabilization"
    return "post_stabilization"


def _fast_path_strategy(emotion: str, intent: str) -> str | None:
    for emotions, intents, strategy in _FAST_PATH:
        emotion_match = not emotions or emotion in emotions
        intent_match = not intents or intent in intents
        if emotion_match and intent_match:
            return strategy
    return None


async def node_therapy_router(state: dict[str, Any]) -> dict[str, Any]:
    emotion: str = state.get("primary_emotion", "neutral")
    intent: str = state.get("intent", "general_health")
    user_input: str = state.get("user_input", "")
    provider: ProviderName = state.get("provider", "openai")
    long_term: dict[str, Any] = state.get("long_term_context") or {}
    flags: dict[str, Any] = state.get("therapy_flags") or {}

    if state.get("objection_detected"):
        return {"therapy_strategy": "reflective_listening"}

    if intent == "casual" or is_meta_conversation(user_input):
        return {"therapy_strategy": "reflective_listening"}

    if intent == "relationship_stress" or has_relationship_context(state):
        if emotion == "hopeless":
            return {"therapy_strategy": resolve_hopeless_strategy(state)}
        return {"therapy_strategy": "reflective_listening"}

    if emotion == "hopeless":
        return {"therapy_strategy": resolve_hopeless_strategy(state)}

    # Post-stabilization without hopeless label
    if flags.get("stabilization_turn") and is_post_stabilization_followup(user_input):
        return {"therapy_strategy": "post_stabilization"}

    fast = _fast_path_strategy(emotion, intent)
    if fast:
        return {"therapy_strategy": fast}

    user_ctx = (
        f"emotion: {emotion}\n"
        f"intent: {intent}\n"
        f"mood_trend: {long_term.get('mood_trend', 'stable')}\n"
        f"coping_preferences: {long_term.get('coping_preferences', [])}"
    )
    try:
        llm = get_chat_model(provider)
        msg = await invoke_with_fallback(
            llm,
            [SystemMessage(content=_SYSTEM), HumanMessage(content=user_ctx)],
            primary=provider,
        )
        raw = msg.content if isinstance(msg.content, str) else str(msg.content)
        m = re.search(r"\{[^{}]+\}", raw, re.DOTALL)
        strategy = "CBT"
        if m:
            try:
                data = json.loads(m.group())
                s = str(data.get("strategy", "CBT"))
                if s in VALID_STRATEGIES:
                    strategy = s
            except json.JSONDecodeError:
                pass
    except Exception as exc:
        logger.warning("therapy_router LLM failed: %s", exc)
        strategy = "CBT"

    return {"therapy_strategy": strategy}
