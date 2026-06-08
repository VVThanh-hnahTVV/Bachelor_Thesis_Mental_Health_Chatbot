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

_CRISIS_STRATEGIES = frozenset({
    "crisis_concern",
    "crisis_listen",
    "crisis_grounding",
    "crisis_safety_check",
    "crisis_reassure",
    "crisis_connect",
    "crisis_resources",
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
    "broke up",
    "broken up",
    "split up",
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

_STILL_STRUGGLING_MARKERS = (
    "không khá hơn",
    "chẳng khá hơn",
    "chưa khá hơn",
    "không đỡ",
    "chưa đỡ",
    "chẳng đỡ",
    "vẫn vậy",
    "vẫn chưa",
    "vẫn không",
    "not better",
    "no better",
    "still the same",
    "doesn't help",
    "does not help",
)

_PHYSICAL_DISTRESS_MARKERS = (
    "tightness in my chest",
    "tightness in chest",
    "lump in my throat",
    "lump in throat",
    "chest tight",
    "can't breathe",
    "cannot breathe",
    "hard to breathe",
    "hyperventilat",
    "khó thở",
    "nghẹn",
    "nghẹn họng",
    "thắt ngực",
    "tức ngực",
    "nóng ruột",
    "body shaking",
    "run rẩy",
    "tim đập",
    "heart racing",
    "knot in my stomach",
    "knot in stomach",
    "stomach in knots",
    "shaking",
    "trembling",
    "dizzy",
    "choáng váng",
    "nauseous",
    "feel sick",
    "đau bụng vì căng",
)

# Intents where the user is processing feelings in the open (not Q&A / education).
_VENTING_INTENTS_FOR_HEALING = frozenset({
    "venting",
    "loneliness",
    "relationship_stress",
    "journaling",
})

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


def is_still_struggling_followup(user_input: str) -> bool:
    """User says calming / prior approach did not help — switch to listening, not more probes."""
    t = user_input.lower().strip()
    return any(m in t for m in _STILL_STRUGGLING_MARKERS)


def has_physical_distress(text: str) -> bool:
    t = text.lower().strip()
    return any(m in t for m in _PHYSICAL_DISTRESS_MARKERS)


def _count_user_turns(history: list[dict[str, str]]) -> int:
    return sum(1 for m in history if m.get("role") == "user")


def is_sustained_emotional_sharing_lane(intent: str, state: dict[str, Any]) -> bool:
    """Open-ended emotional processing: venting, grief, loneliness, journals, or relationship pain."""
    if intent in _VENTING_INTENTS_FOR_HEALING:
        return True
    if has_relationship_context(state):
        return True
    return False


def resolve_venting_regulation_strategy(state: dict[str, Any]) -> str:
    """Listen first; after enough reflective turns or somatic cues, offer grounding (avoid over-probing)."""
    user_input: str = state.get("user_input", "")
    history: list[dict[str, str]] = state.get("history") or []
    flags: dict[str, Any] = state.get("therapy_flags") or {}
    blob = _user_blob(state)

    if has_physical_distress(user_input) or has_physical_distress(blob):
        return "grounding"

    reflective_turns = int(flags.get("reflective_listening_turns") or 0)
    user_turns = _count_user_turns(history) + 1

    # After several reflective turns, shift to grounding offer (Wysa-style healing step)
    if reflective_turns >= 2 and flags.get("last_strategy") == "reflective_listening":
        return "grounding"
    if user_turns >= 4 and flags.get("last_strategy") == "reflective_listening":
        return "grounding"

    return "reflective_listening"


def resolve_hopeless_strategy(state: dict[str, Any]) -> str:
    """First hopeless turn → stabilization; once → post_stabilization; then reflective listening."""
    flags: dict[str, Any] = state.get("therapy_flags") or {}
    user_input: str = state.get("user_input", "")

    if flags.get("last_strategy") == "post_stabilization":
        return "reflective_listening"
    if flags.get("stabilization_turn") and is_still_struggling_followup(user_input):
        return "reflective_listening"

    if flags.get("stabilization_turn") and (
        is_post_stabilization_followup(user_input)
        or flags.get("last_strategy") == "stabilization"
    ):
        intent: str = state.get("intent", "general_health")
        if is_sustained_emotional_sharing_lane(intent, state):
            return "post_stabilization"
        return "CBT"
    if not flags.get("stabilization_turn"):
        return "stabilization"
    return "reflective_listening"


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

    forced = state.get("force_therapy_strategy")
    if forced in VALID_STRATEGIES or forced in _CRISIS_STRATEGIES:
        return {"therapy_strategy": str(forced)}

    if state.get("objection_detected"):
        return {"therapy_strategy": "reflective_listening"}

    if intent == "casual" or is_meta_conversation(user_input):
        return {"therapy_strategy": "reflective_listening"}

    if emotion == "hopeless":
        return {"therapy_strategy": resolve_hopeless_strategy(state)}

    # Latest message names body distress → regulate before more verbal exploration
    if has_physical_distress(user_input) and intent != "psychoeducation":
        return {"therapy_strategy": "grounding"}

    if is_sustained_emotional_sharing_lane(intent, state):
        return {"therapy_strategy": resolve_venting_regulation_strategy(state)}

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
