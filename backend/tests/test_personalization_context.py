import pytest

from app.personalization.context import build_personalization_context


@pytest.mark.asyncio
async def test_build_personalization_context_includes_mood_and_profile(monkeypatch):
    async def fake_list_mood_entries(_db, *, session_id, limit):
        assert session_id == "session-12345678"
        assert limit >= 1
        return [
            {"score": 4, "note": "Rat met moi"},
            {"score": 6, "note": "Da do hon"},
        ]

    async def fake_get_user_profile(_db, _session_id):
        return {
            "recurring_stressors": ["cong viec"],
            "coping_preferences": ["di bo"],
            "preferred_tone": "gentle",
        }

    async def fake_get_mood_trend(_db, _session_id):
        return "improving"

    async def fake_get_session_link(_db, _session_id):
        return {"user_id": "not-object-id"}

    monkeypatch.setattr(
        "app.personalization.context.list_mood_entries",
        fake_list_mood_entries,
    )
    monkeypatch.setattr(
        "app.personalization.context.get_user_profile",
        fake_get_user_profile,
    )
    monkeypatch.setattr(
        "app.personalization.context.get_mood_trend",
        fake_get_mood_trend,
    )
    monkeypatch.setattr(
        "app.personalization.context.get_session_link_by_session_id",
        fake_get_session_link,
    )

    ctx = await build_personalization_context(
        object(),
        session_id="session-12345678",
        include_user_display=False,
    )

    assert ctx["mood_trend"] == "improving"
    assert ctx["recent_mood_scores"] == [4, 6]
    assert ctx["recurring_stressors"] == ["cong viec"]
    assert ctx["coping_preferences"] == ["di bo"]
    assert ctx["preferred_tone"] == "gentle"
