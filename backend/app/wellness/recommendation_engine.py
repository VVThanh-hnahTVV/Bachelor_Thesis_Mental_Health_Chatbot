"""Hybrid recommendation engine: when and how strongly to offer wellness activities.

Pipeline:
  1. Hard gates  — risk_level, objection, early venting, cooldown
  2. Explicit request — always honour ("cho tôi bài thở")
  3. Conversation state × emotion × intent → rule-based activity mapping
  4. Personalization scoring — boost/suppress via ActivityProfile
  5. Intensity classification — soft / medium / strong CTA level

References:
  - Wysa: https://www.wysa.io  (pacing model)
  - ConvState machine in conversation_state.py
"""
from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Any

from app.wellness.activity_profile import ActivityProfile
from app.wellness.conversation_state import ConvState

# ---------------------------------------------------------------------------
# Tuneable thresholds
# ---------------------------------------------------------------------------

MIN_TURNS_FOR_PROACTIVE = 4   # turns before any unsolicited CTA
MIN_TURNS_WHILE_VENTING = 5   # extra buffer in VENTING phase
COOLDOWN_TURNS = 4            # turns between proactive suggestions

# ---------------------------------------------------------------------------
# Intent / emotion sets
# ---------------------------------------------------------------------------

VENTING_INTENTS = frozenset({
    "venting",
    "loneliness",
    "journaling",
    "relationship_stress",
})

NEGATIVE_EMOTIONS = frozenset({
    "anxiety",
    "sadness",
    "anger",
    "hopeless",
    "overwhelmed",
    "lonely",
    "grief",
    "fear",
})

# ---------------------------------------------------------------------------
# Keyword helpers (LLM handles semantic gaps; keywords = fast-path triggers)
# ---------------------------------------------------------------------------

_STRESS_KEYWORDS_VI = (
    "stress", "căng thẳng", "lo âu", "lo lắng", "mệt", "mệt mỏi",
    "kiệt sức", "burnout", "không ngủ", "mất ngủ", "không muốn", "chán", "buồn",
)
_STRESS_KEYWORDS_EN = (
    "stressed", "anxious", "worried", "tired", "exhausted", "burnout",
    "can't sleep", "insomnia", "don't want to", "hopeless",
)

_EXPLICIT_BREATH = (
    "hít thở", "thở sâu", "bài tập thở", "breathing", "breath exercise", "box breathing",
)
_EXPLICIT_CALM_AUDIO = (
    "âm sóng", "nghe nhạc", "nhạc thư giãn", "ocean", "ambient",
    "calming sound", "relaxing music",
)


# ---------------------------------------------------------------------------
# Data models
# ---------------------------------------------------------------------------

class SuggestionIntensity(str, Enum):
    """How strongly the system frames the CTA.

    soft   → "Có lúc bài thở ngắn có thể giúp..."
    medium → "Bạn muốn thử bài thở 2 phút không?"
    strong → "Mình nghĩ grounding sẽ giúp bạn ngay lúc này."
    """
    SOFT = "soft"
    MEDIUM = "medium"
    STRONG = "strong"


@dataclass
class RecommendationSignals:
    user_input: str
    assistant_reply: str
    intent: str
    primary_emotion: str
    emotion_intensity: float
    therapy_strategy: str | None
    user_turn_count: int
    risk_level: str
    history: list[dict[str, str]] = field(default_factory=list)
    turns_since_last_suggestion: int | None = None
    objection_detected: bool = False
    conv_state: ConvState = ConvState.OPENING
    activity_profile: ActivityProfile = field(default_factory=ActivityProfile)


@dataclass
class RecommendationDecision:
    eligible: bool
    activity_ids: list[str] = field(default_factory=list)
    intensity: SuggestionIntensity = SuggestionIntensity.MEDIUM
    use_llm_planner: bool = False
    allow_keyword_fallback: bool = False
    reason: str = ""


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------

def _norm(text: str) -> str:
    return text.lower().strip()


def _explicit_activity_ids(user_input: str) -> list[str]:
    t = _norm(user_input)
    ids: list[str] = []
    if any(c in t for c in _EXPLICIT_BREATH):
        ids.append("breathing_box")
    if any(c in t for c in _EXPLICIT_CALM_AUDIO) and "ocean_sound" not in ids:
        ids.append("ocean_sound")
    return ids[:2]


def _negative_keyword_hits(text: str) -> int:
    t = _norm(text)
    return (
        sum(1 for k in _STRESS_KEYWORDS_VI if k in t)
        + sum(1 for k in _STRESS_KEYWORDS_EN if k in t)
    )


def _sustained_negative_streak(history: list[dict[str, str]], current: str) -> int:
    """Consecutive recent user turns with stress keywords (including current)."""
    user_lines = [m.get("content", "") for m in history if m.get("role") == "user"]
    user_lines.append(current)
    streak = 0
    for line in reversed(user_lines[-6:]):
        if _negative_keyword_hits(line) >= 1:
            streak += 1
        else:
            break
    return streak


def _is_early_venting(signals: RecommendationSignals) -> bool:
    if signals.intent not in VENTING_INTENTS:
        return False
    if signals.conv_state == ConvState.VENTING:
        return signals.user_turn_count < MIN_TURNS_WHILE_VENTING
    return signals.user_turn_count < MIN_TURNS_FOR_PROACTIVE


def _apply_personalization(
    ids: list[str],
    profile: ActivityProfile,
    intensity: SuggestionIntensity,
) -> tuple[list[str], SuggestionIntensity]:
    """Re-order ids by preference score; lower intensity if user has rarely completed."""
    if not ids:
        return ids, intensity

    preferred = profile.preferred_ids()
    # Sort ids by preferred order (unseen activities stay in original order)
    ordered = sorted(ids, key=lambda x: preferred.index(x) if x in preferred else 99)

    # Suppress entirely if all are rejected
    active = [aid for aid in ordered if aid not in profile.rejected_ids]
    if not active:
        return [], intensity

    # If user typically bails on the top activity, soften the tone
    top = active[0]
    score = profile.boost_score(top)
    if score < -0.1:
        new_intensity = SuggestionIntensity.SOFT
    elif score >= 0.25:
        new_intensity = SuggestionIntensity.STRONG if intensity == SuggestionIntensity.MEDIUM else intensity
    else:
        new_intensity = intensity

    return active[:2], new_intensity


def _intensity_from_state_and_emotion(
    conv_state: ConvState,
    emotion: str,
    intensity: float,
    therapy_strategy: str | None,
) -> SuggestionIntensity:
    """Map conversation context to a CTA intensity level."""
    strategy = therapy_strategy or ""

    if conv_state == ConvState.REGULATION or strategy in ("grounding", "stabilization"):
        if intensity >= 0.7:
            return SuggestionIntensity.STRONG
        return SuggestionIntensity.MEDIUM

    if conv_state == ConvState.EXPLORATION:
        return SuggestionIntensity.MEDIUM

    if conv_state in (ConvState.REFLECTION, ConvState.CLOSING):
        return SuggestionIntensity.SOFT

    # VENTING — always soften
    if conv_state == ConvState.VENTING:
        return SuggestionIntensity.SOFT

    # OPENING / default — gentle unless high intensity
    if intensity >= 0.75:
        return SuggestionIntensity.MEDIUM
    return SuggestionIntensity.SOFT


# ---------------------------------------------------------------------------
# Main decision function
# ---------------------------------------------------------------------------

def evaluate_recommendation(signals: RecommendationSignals) -> RecommendationDecision:
    """Decide whether, what, and how strongly to suggest an activity."""

    # ── Hard gates ──────────────────────────────────────────────────────────
    if signals.risk_level == "high":
        return RecommendationDecision(False, reason="high_risk")

    if signals.objection_detected:
        return RecommendationDecision(False, reason="objection")

    if signals.conv_state == ConvState.CRISIS:
        return RecommendationDecision(False, reason="crisis_state")

    # ── Explicit user request (always honour) ───────────────────────────────
    explicit = _explicit_activity_ids(signals.user_input)
    if explicit:
        ids, intensity = _apply_personalization(
            explicit, signals.activity_profile, SuggestionIntensity.MEDIUM
        )
        return RecommendationDecision(
            True,
            activity_ids=ids or explicit,
            intensity=SuggestionIntensity.MEDIUM,
            reason="explicit_user_request",
        )

    # ── Cooldown (skip spam) ─────────────────────────────────────────────────
    if (
        signals.turns_since_last_suggestion is not None
        and signals.turns_since_last_suggestion < COOLDOWN_TURNS
    ):
        return RecommendationDecision(False, reason="cooldown")

    # ── Too early / deep venting ─────────────────────────────────────────────
    if _is_early_venting(signals):
        return RecommendationDecision(False, reason="early_venting_listen_first")

    if signals.user_turn_count < MIN_TURNS_FOR_PROACTIVE:
        return RecommendationDecision(False, reason="too_early_in_session")

    # ── Not during active wellness session ───────────────────────────────────
    if signals.conv_state == ConvState.REFLECTION and signals.turns_since_last_suggestion is not None:
        # After a completed activity, give breathing room
        if signals.turns_since_last_suggestion < 2:
            return RecommendationDecision(False, reason="post_activity_cooldown")

    # ── State × Emotion → activity mapping ───────────────────────────────────
    emotion = _norm(signals.primary_emotion or "neutral")
    intensity_val = max(0.0, min(1.0, float(signals.emotion_intensity or 0.5)))
    strategy = signals.therapy_strategy or ""
    intent = signals.intent or ""
    state = signals.conv_state

    base_intensity = _intensity_from_state_and_emotion(state, emotion, intensity_val, strategy)

    # REGULATION / grounding — highest priority
    if state == ConvState.REGULATION or strategy in ("grounding", "stabilization"):
        if emotion in ("anxiety", "overwhelmed", "fear") and intensity_val >= 0.5:
            ids, adj_intensity = _apply_personalization(
                ["breathing_box"], signals.activity_profile, base_intensity
            )
            return RecommendationDecision(True, activity_ids=ids, intensity=adj_intensity, reason="regulation_breathing")

    # Sleep intent — ocean wind-down (works from early turns)
    if intent == "sleep_issues":
        if signals.user_turn_count >= 2:
            ids, adj_intensity = _apply_personalization(
                ["ocean_sound"], signals.activity_profile, SuggestionIntensity.MEDIUM
            )
            return RecommendationDecision(True, activity_ids=ids, intensity=adj_intensity, reason="sleep_wind_down")

    # Panic grounding
    if intent == "panic_support" and intensity_val >= 0.55:
        ids, adj_intensity = _apply_personalization(
            ["breathing_box"], signals.activity_profile, SuggestionIntensity.STRONG
        )
        return RecommendationDecision(True, activity_ids=ids, intensity=adj_intensity, reason="panic_grounding")

    # Sustained negative streak (≥3 consecutive user turns with stress keywords)
    streak = _sustained_negative_streak(signals.history, signals.user_input)
    if streak >= 3 and signals.user_turn_count >= MIN_TURNS_WHILE_VENTING:
        if emotion in ("anxiety", "overwhelmed", "fear") and intensity_val >= 0.5:
            ids, adj_intensity = _apply_personalization(
                ["breathing_box"], signals.activity_profile, base_intensity
            )
            return RecommendationDecision(True, activity_ids=ids, intensity=adj_intensity, reason="sustained_stress_anxiety")
        if emotion in ("sadness", "hopeless", "lonely", "grief"):
            ids, adj_intensity = _apply_personalization(
                ["ocean_sound"], signals.activity_profile, SuggestionIntensity.SOFT
            )
            return RecommendationDecision(True, activity_ids=ids, intensity=adj_intensity, reason="sustained_low_mood")

    # Advice-seeking with anxiety — try LLM planner with medium confidence
    if intent in ("seeking_advice", "general_health") and intensity_val >= 0.55:
        if emotion in ("anxiety", "overwhelmed", "fear") and state != ConvState.VENTING:
            return RecommendationDecision(
                True,
                use_llm_planner=True,
                intensity=SuggestionIntensity.MEDIUM,
                reason="advice_seeking_anxiety_llm",
            )

    # Ambiguous high-intensity — allow LLM only after enough conversation depth
    if (
        signals.user_turn_count >= MIN_TURNS_FOR_PROACTIVE
        and emotion in NEGATIVE_EMOTIONS
        and intensity_val >= 0.65
        and strategy not in ("reflective_listening", "stabilization")
        and intent not in VENTING_INTENTS
        and state not in (ConvState.VENTING, ConvState.CRISIS)
    ):
        return RecommendationDecision(
            True,
            use_llm_planner=True,
            intensity=SuggestionIntensity.SOFT,
            reason="ambiguous_high_intensity_llm",
        )

    return RecommendationDecision(False, reason="not_right_moment")


# ---------------------------------------------------------------------------
# Micro-feedback eligibility
# ---------------------------------------------------------------------------

def should_show_activity_micro_feedback(
    *,
    user_turn_count: int,
    intent: str,
    therapy_strategy: str | None,
    reply: str,
    suggested_activities: list[Any],
    objection_detected: bool,
    conv_state: ConvState = ConvState.OPENING,
) -> bool:
    """Show 'did this help?' only after a real intervention, not mid-vent."""
    if objection_detected:
        return False
    if user_turn_count < MIN_TURNS_WHILE_VENTING:
        return False
    if not suggested_activities:
        return False
    # Never interrupt early venting phase
    if conv_state == ConvState.VENTING and user_turn_count < MIN_TURNS_WHILE_VENTING + 2:
        return False
    if intent in VENTING_INTENTS and therapy_strategy == "reflective_listening":
        return user_turn_count >= MIN_TURNS_WHILE_VENTING + 2
    if len(reply.strip()) < 100:
        return False
    return True


# ---------------------------------------------------------------------------
# Implicit PHQ-2 — infer depression signal from conversation history
# ---------------------------------------------------------------------------

# Keywords signalling anhedonia (Q1: little interest / pleasure)
_ANHEDONIA_VI = (
    "không muốn", "chẳng muốn", "không hứng thú", "mất hứng",
    "không thiết", "không còn muốn", "thờ ơ", "chán nản", "vô nghĩa",
    "không có ý nghĩa", "không còn hứng",
)
_ANHEDONIA_EN = (
    "don't want to", "no interest", "pointless", "meaningless",
    "can't enjoy", "no motivation", "lost interest", "don't care anymore",
)


def implicit_phq2_scores(message_docs: list[dict[str, Any]]) -> tuple[int, int]:
    """Infer PHQ-2 Q1 and Q2 scores (0–3 each) from MongoDB message documents.

    Uses emotion/intent/intensity stored in assistant message metadata and
    keyword patterns in user message content — no explicit survey needed.

    Returns:
        (q1, q2) where:
          q1 = anhedonia (little interest or pleasure in doing things)
          q2 = depressed mood (feeling down, hopeless, or empty)
        Total ≥ 3 indicates a clinically relevant signal worth attention.
    """
    recent = message_docs[-20:]  # up to ~10 conversation turns

    assistant_meta: list[dict[str, Any]] = [
        m.get("metadata") or {}
        for m in recent
        if m.get("role") == "assistant"
    ]
    user_contents: list[str] = [
        (m.get("content") or "").lower()
        for m in recent
        if m.get("role") == "user"
    ]

    n_asst = max(len(assistant_meta), 1)
    n_user = max(len(user_contents), 1)

    # ── Q2: depressed mood ──────────────────────────────────────────────────
    _DEPRESSED_EMOTIONS = {"hopeless", "sadness", "grief"}
    depressed_turns = [
        m for m in assistant_meta
        if m.get("emotion") in _DEPRESSED_EMOTIONS
    ]
    depressed_ratio = len(depressed_turns) / n_asst
    max_depressed_intensity = max(
        (float(m.get("emotion_intensity") or 0.0) for m in depressed_turns),
        default=0.0,
    )

    if depressed_ratio >= 0.70 or max_depressed_intensity >= 0.85:
        q2 = 3
    elif depressed_ratio >= 0.40 or max_depressed_intensity >= 0.65:
        q2 = 2
    elif depressed_ratio >= 0.20 or max_depressed_intensity >= 0.45:
        q2 = 1
    else:
        q2 = 0

    # ── Q1: anhedonia ────────────────────────────────────────────────────────
    # Signal A: emotion-based — hopeless/overwhelmed + venting-type intent
    _ANHEDONIA_EMOTIONS = {"hopeless", "overwhelmed"}
    _ANHEDONIA_INTENTS = {"venting", "loneliness", "journaling"}
    anhedonia_emotion_turns = [
        m for m in assistant_meta
        if m.get("emotion") in _ANHEDONIA_EMOTIONS
        and m.get("intent") in _ANHEDONIA_INTENTS
    ]
    emotion_signal = len(anhedonia_emotion_turns) / n_asst

    # Signal B: keyword scan on user messages
    keyword_hits = sum(
        1 for content in user_contents
        if any(k in content for k in _ANHEDONIA_VI)
        or any(k in content for k in _ANHEDONIA_EN)
    )
    keyword_signal = keyword_hits / n_user

    combined = max(emotion_signal, keyword_signal)

    if combined >= 0.60:
        q1 = 3
    elif combined >= 0.35:
        q1 = 2
    elif combined >= 0.15:
        q1 = 1
    else:
        q1 = 0

    return q1, q2


def depression_level(q1: int, q2: int) -> str:
    """Classify implicit PHQ-2 total into a named level.

    0–1 → "none" | 2–3 → "mild" | 4–5 → "moderate" | 6 → "high"
    """
    total = q1 + q2
    if total >= 6:
        return "high"
    if total >= 4:
        return "moderate"
    if total >= 2:
        return "mild"
    return "none"
