"""Conversation State Machine (Redis-backed).

Tracks where the user is emotionally in a session so the system can pace
its interventions — mirroring how a real therapist reads the room.

State transitions:
    OPENING → VENTING (first negative share)
    VENTING → EXPLORATION (user asks / shifts to insight)
    VENTING → REGULATION (acute panic/overwhelm)
    EXPLORATION → REGULATION (anxiety spikes during exploration)
    EXPLORATION → REFLECTION (insight reached)
    REGULATION → REFLECTION (after calming activity)
    REFLECTION → CLOSING (session winds down naturally)
    any → CRISIS (safety engine triggers)
"""
from __future__ import annotations

import json
from enum import Enum
from typing import Any

from redis.asyncio import Redis

TTL_SEC = 7200


class ConvState(str, Enum):
    OPENING = "opening"
    VENTING = "venting"
    EXPLORATION = "exploration"
    REGULATION = "regulation"
    REFLECTION = "reflection"
    CLOSING = "closing"
    CRISIS = "crisis"


# Intents that signal a venting phase
_VENTING_INTENTS = frozenset({
    "venting",
    "loneliness",
    "relationship_stress",
    "journaling",
})

# Intents that signal the user is ready to explore / seek solutions
_EXPLORATION_INTENTS = frozenset({
    "seeking_advice",
    "general_health",
    "sleep_issues",
})

_REGULATION_STRATEGIES = frozenset({"grounding", "stabilization"})
_REFLECTION_STRATEGIES = frozenset({"reflective_listening", "CBT", "behavioral_activation"})


def _key(session_id: str) -> str:
    return f"conv_state:{session_id}"


async def get_conv_state(redis: Redis | None, session_id: str) -> ConvState:
    if redis is None:
        return ConvState.OPENING
    raw = await redis.get(_key(session_id))
    if not raw:
        return ConvState.OPENING
    try:
        return ConvState(raw.decode() if isinstance(raw, bytes) else raw)
    except ValueError:
        return ConvState.OPENING


async def _set_state(redis: Redis, session_id: str, state: ConvState) -> None:
    await redis.set(_key(session_id), state.value, ex=TTL_SEC)


async def advance_conv_state(
    redis: Redis | None,
    *,
    session_id: str,
    intent: str,
    primary_emotion: str,
    emotion_intensity: float,
    therapy_strategy: str | None,
    risk_level: str,
    user_turn_count: int,
    wellness_activity_just_completed: bool = False,
) -> ConvState:
    """Compute next state and persist it. Returns the new state."""
    if redis is None:
        return _transition_pure(
            current=ConvState.OPENING,
            intent=intent,
            primary_emotion=primary_emotion,
            emotion_intensity=emotion_intensity,
            therapy_strategy=therapy_strategy,
            risk_level=risk_level,
            user_turn_count=user_turn_count,
            wellness_activity_just_completed=wellness_activity_just_completed,
        )

    current = await get_conv_state(redis, session_id)
    next_state = _transition_pure(
        current=current,
        intent=intent,
        primary_emotion=primary_emotion,
        emotion_intensity=emotion_intensity,
        therapy_strategy=therapy_strategy,
        risk_level=risk_level,
        user_turn_count=user_turn_count,
        wellness_activity_just_completed=wellness_activity_just_completed,
    )
    if next_state != current:
        await _set_state(redis, session_id, next_state)
    return next_state


def _transition_pure(
    *,
    current: ConvState,
    intent: str,
    primary_emotion: str,
    emotion_intensity: float,
    therapy_strategy: str | None,
    risk_level: str,
    user_turn_count: int,
    wellness_activity_just_completed: bool,
) -> ConvState:
    """Pure transition function — no I/O, fully testable."""

    # CRISIS overrides everything
    if risk_level == "high":
        return ConvState.CRISIS

    # Recover from CRISIS only when risk drops
    if current == ConvState.CRISIS:
        if risk_level in ("low", "medium"):
            return ConvState.REGULATION
        return ConvState.CRISIS

    # Activity just completed → move toward reflection
    if wellness_activity_just_completed:
        if current in (ConvState.REGULATION, ConvState.VENTING):
            return ConvState.REFLECTION
        return current

    strategy = therapy_strategy or ""

    match current:
        case ConvState.OPENING:
            if intent in _VENTING_INTENTS or primary_emotion in (
                "sadness", "grief", "lonely", "anger", "fear", "hopeless"
            ):
                return ConvState.VENTING
            if intent in _EXPLORATION_INTENTS:
                return ConvState.EXPLORATION
            if strategy in _REGULATION_STRATEGIES or (
                primary_emotion in ("anxiety", "overwhelmed") and emotion_intensity >= 0.7
            ):
                return ConvState.REGULATION
            return ConvState.OPENING

        case ConvState.VENTING:
            # Acute escalation → regulate first
            if primary_emotion in ("anxiety", "overwhelmed") and emotion_intensity >= 0.75:
                return ConvState.REGULATION
            # After enough turns, natural shift to exploration
            if intent in _EXPLORATION_INTENTS and user_turn_count >= 4:
                return ConvState.EXPLORATION
            # User reached insight
            if strategy in _REFLECTION_STRATEGIES and user_turn_count >= 6:
                return ConvState.REFLECTION
            return ConvState.VENTING

        case ConvState.EXPLORATION:
            if primary_emotion in ("anxiety", "overwhelmed") and emotion_intensity >= 0.7:
                return ConvState.REGULATION
            if strategy in _REFLECTION_STRATEGIES and intent not in _VENTING_INTENTS:
                if user_turn_count >= 5:
                    return ConvState.REFLECTION
            return ConvState.EXPLORATION

        case ConvState.REGULATION:
            # After calming, move to reflection
            if emotion_intensity <= 0.45 and user_turn_count >= 3:
                return ConvState.REFLECTION
            return ConvState.REGULATION

        case ConvState.REFLECTION:
            # Natural wind-down signals
            if intent == "casual" and user_turn_count >= 8:
                return ConvState.CLOSING
            return ConvState.REFLECTION

        case ConvState.CLOSING:
            return ConvState.CLOSING

    return current
