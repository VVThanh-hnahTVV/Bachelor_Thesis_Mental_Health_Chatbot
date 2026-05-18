"""Per-user activity preference profile (lightweight personalization).

Builds a usage summary from `activity_completions` and optional micro-feedback.
No ML — just simple counts and recency weighting to boost/suppress activities.
"""
from __future__ import annotations

import asyncio
from dataclasses import dataclass, field
from typing import Any

from motor.motor_asyncio import AsyncIOMotorDatabase

ALLOWED_IDS = frozenset({"breathing_box", "ocean_sound"})

# Completion count thresholds
_HIGH_COMPLETION = 3   # user completes this a lot → boost it
_NO_COMPLETION_PENALTY_AFTER = 2  # completed 0 times after 2+ attempts → suppress a bit

# Duration thresholds (seconds) — short = user bailed early
_SHORT_COMPLETION_SEC = 30


@dataclass
class ActivityProfile:
    """Preference summary for a single user."""
    completion_counts: dict[str, int] = field(default_factory=dict)
    # total attempts (including incomplete) per activity
    attempt_counts: dict[str, int] = field(default_factory=dict)
    # average duration per activity (seconds), None if no data
    avg_duration: dict[str, float | None] = field(default_factory=dict)
    # ids the user has explicitly rejected via breathing refusal
    rejected_ids: set[str] = field(default_factory=set)
    # most recently completed activity id
    last_completed_id: str | None = None
    last_activity_was_recent: bool = False  # completed in last session

    def boost_score(self, activity_id: str) -> float:
        """Return a [-1, +1] score modifier based on history."""
        if activity_id in self.rejected_ids:
            return -1.0
        count = self.completion_counts.get(activity_id, 0)
        if count >= _HIGH_COMPLETION:
            return 0.3
        if count == 0 and self.attempt_counts.get(activity_id, 0) >= _NO_COMPLETION_PENALTY_AFTER:
            return -0.2
        dur = self.avg_duration.get(activity_id)
        if dur is not None and dur < _SHORT_COMPLETION_SEC:
            return -0.15
        return 0.0

    def preferred_ids(self) -> list[str]:
        """Return activity ids sorted by user preference (best first)."""
        scored = [
            (aid, self.boost_score(aid))
            for aid in ALLOWED_IDS
            if aid not in self.rejected_ids
        ]
        scored.sort(key=lambda x: x[1], reverse=True)
        return [aid for aid, _ in scored]


async def load_activity_profile(
    db: AsyncIOMotorDatabase | None,
    session_id: str,
) -> ActivityProfile:
    """Fetch completions + profile from Mongo; return empty profile if unavailable."""
    if db is None:
        return ActivityProfile()

    from app.db.repository import list_activity_completions, get_user_profile

    try:
        completions_task = asyncio.create_task(
            list_activity_completions(db, session_id=session_id, limit=50)
        )
        profile_task = asyncio.create_task(get_user_profile(db, session_id))
        completions, raw_profile = await asyncio.gather(completions_task, profile_task)
    except Exception:
        return ActivityProfile()

    prof = ActivityProfile()

    # Build completion stats
    completion_counts: dict[str, int] = {}
    durations: dict[str, list[float]] = {}
    last_id: str | None = None

    for doc in completions:
        aid = str(doc.get("activity_id", ""))
        if aid not in ALLOWED_IDS:
            continue
        completion_counts[aid] = completion_counts.get(aid, 0) + 1
        dur = doc.get("duration_sec")
        if dur is not None:
            durations.setdefault(aid, []).append(float(dur))
        if last_id is None:
            last_id = aid

    prof.completion_counts = completion_counts
    prof.last_completed_id = last_id

    for aid, dur_list in durations.items():
        if dur_list:
            prof.avg_duration[aid] = sum(dur_list) / len(dur_list)

    # Extract rejected activities from coping_preferences in long-term profile
    if raw_profile:
        coping = raw_profile.get("coping_preferences") or []
        for pref in coping:
            if "không thở" in str(pref).lower() or "no breathing" in str(pref).lower():
                prof.rejected_ids.add("breathing_box")

    return prof
