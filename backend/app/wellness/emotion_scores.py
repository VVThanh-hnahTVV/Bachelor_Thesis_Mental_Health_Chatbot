"""Map chat-classified emotions to wellness scores for dashboard display."""
from __future__ import annotations

from collections import Counter
from datetime import UTC, datetime
from typing import Any

# Base wellness score (0–100) per detected primary_emotion label.
_EMOTION_BASE: dict[str, int] = {
    "joy": 88,
    "neutral": 55,
    "anxiety": 38,
    "sadness": 32,
    "anger": 35,
    "hopeless": 18,
    "overwhelmed": 28,
    "lonely": 30,
    "grief": 25,
    "fear": 34,
    "shame": 28,
    "guilt": 30,
}

_POSITIVE = frozenset({"joy", "neutral"})
_NEGATIVE = frozenset(
    {
        "anxiety",
        "sadness",
        "anger",
        "hopeless",
        "overwhelmed",
        "lonely",
        "grief",
        "fear",
        "shame",
        "guilt",
    }
)


def emotion_to_score(emotion: str, intensity: float | None = None) -> int:
    """Convert an emotion label (+ optional 0–1 intensity) to a 0–100 wellness score."""
    key = (emotion or "neutral").strip().lower()
    base = _EMOTION_BASE.get(key, 50)
    if intensity is None:
        return base
    i = max(0.0, min(1.0, float(intensity)))
    if key in _POSITIVE:
        delta = int((i - 0.5) * 24)
    elif key in _NEGATIVE:
        delta = int((0.5 - i) * 24)
    else:
        delta = 0
    return max(0, min(100, base + delta))


def _parse_created_at(value: Any) -> datetime | None:
    if isinstance(value, datetime):
        return value if value.tzinfo else value.replace(tzinfo=UTC)
    if isinstance(value, str):
        try:
            parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
            return parsed if parsed.tzinfo else parsed.replace(tzinfo=UTC)
        except ValueError:
            return None
    return None


def _is_today(dt: datetime, *, day_start: datetime) -> bool:
    from datetime import timedelta

    end = day_start + timedelta(days=1)
    return day_start <= dt < end


def aggregate_chat_emotions_today(
    message_docs: list[dict[str, Any]],
    *,
    day_start: datetime | None = None,
) -> dict[str, Any]:
    """Extract today's assistant emotion samples from MongoDB message documents."""
    start = day_start or datetime.now(UTC).replace(hour=0, minute=0, second=0, microsecond=0)

    scores: list[int] = []
    labels: list[str] = []

    for doc in message_docs:
        if doc.get("role") != "assistant":
            continue
        created = _parse_created_at(doc.get("created_at"))
        if created is None or not _is_today(created, day_start=start):
            continue
        meta = doc.get("metadata") or {}
        if not isinstance(meta, dict):
            continue
        emotion = meta.get("emotion")
        if not emotion or not isinstance(emotion, str):
            continue
        label = emotion.strip().lower()
        intensity_raw = meta.get("emotion_intensity")
        intensity = float(intensity_raw) if intensity_raw is not None else None
        scores.append(emotion_to_score(label, intensity))
        labels.append(label)

    if not scores:
        return {
            "mood_score": None,
            "dominant_emotion": None,
            "samples": 0,
        }

    dominant = Counter(labels).most_common(1)[0][0]
    return {
        "mood_score": round(sum(scores) / len(scores)),
        "dominant_emotion": dominant,
        "samples": len(scores),
    }
