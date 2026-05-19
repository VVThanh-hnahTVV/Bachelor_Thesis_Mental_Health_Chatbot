from __future__ import annotations

from typing import Any

from bson import ObjectId
from motor.motor_asyncio import AsyncIOMotorDatabase

from app.auth.repository import get_session_link_by_session_id, get_user_by_id
from app.config import get_settings
from app.db.repository import get_mood_trend, get_user_profile, list_mood_entries


def _short_text(value: str, max_chars: int = 180) -> str:
    trimmed = value.strip()
    if len(trimmed) <= max_chars:
        return trimmed
    return f"{trimmed[: max_chars - 3]}..."


async def build_personalization_context(
    db: AsyncIOMotorDatabase,
    *,
    session_id: str,
    include_user_display: bool = True,
) -> dict[str, Any]:
    s = get_settings()
    mood_limit = max(1, s.personalization_recent_mood_limit)
    note_limit = max(0, s.personalization_recent_note_limit)

    mood_rows = await list_mood_entries(db, session_id=session_id, limit=mood_limit)
    mood_scores = [int(row.get("score", 0)) for row in mood_rows if row.get("score") is not None]
    notes: list[str] = []
    for row in reversed(mood_rows):
        note = row.get("note")
        if isinstance(note, str) and note.strip():
            notes.append(_short_text(note))
        if len(notes) >= note_limit:
            break

    profile = await get_user_profile(db, session_id)
    trend = await get_mood_trend(db, session_id)

    context: dict[str, Any] = {
        "mood_trend": trend,
        "recent_mood_scores": mood_scores,
        "recent_mood_notes": notes,
        "recurring_stressors": [],
        "coping_preferences": [],
        "preferred_tone": "warm",
    }
    if profile:
        context["recurring_stressors"] = list(profile.get("recurring_stressors") or [])
        context["coping_preferences"] = list(profile.get("coping_preferences") or [])
        context["preferred_tone"] = str(profile.get("preferred_tone") or "warm")

    if include_user_display:
        link = await get_session_link_by_session_id(db, session_id)
        if link:
            user_oid = link.get("user_id")
            if isinstance(user_oid, ObjectId):
                user = await get_user_by_id(db, user_oid)
                if user and isinstance(user.get("name"), str):
                    context["user_display_name"] = user["name"]

    return context
