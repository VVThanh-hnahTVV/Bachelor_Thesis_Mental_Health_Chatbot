import pytest

from app.wellness import suggestions as sugg_mod
from app.wellness.suggestions import (
    _activity_planner_strategy,
    _fallback_activity_ids,
    _parse_activity_id_list,
    _user_refuses_breathing,
    align_assistant_reply_with_suggestions,
    detect_suggested_activities_llm,
)


def test_activity_planner_strategy_env(monkeypatch):
    monkeypatch.delenv("WELLNESS_ACTIVITY_PLANNER", raising=False)
    assert _activity_planner_strategy() == "tool_first"
    monkeypatch.setenv("WELLNESS_ACTIVITY_PLANNER", "json_only")
    assert sugg_mod._activity_planner_strategy() == "json_only"
    monkeypatch.setenv("WELLNESS_ACTIVITY_PLANNER", "tool_only")
    assert sugg_mod._activity_planner_strategy() == "tool_only"


def test_user_refuses_breathing():
    assert _user_refuses_breathing("Đéo hít, đừng bảo tôi thở")
    assert _user_refuses_breathing("không muốn thở nữa")
    assert not _user_refuses_breathing("Tôi hơi lo")


def test_fallback_skips_breathing_when_user_refused():
    ids = _fallback_activity_ids("đéo hít", "Hãy hít thở sâu nhé")
    assert "breathing_box" not in ids


def test_fallback_breathing_when_explicit_cues():
    ids = _fallback_activity_ids("cho tôi bài hít thở", "ok")
    assert "breathing_box" in ids


def test_fallback_ocean_for_music_cue():
    ids = _fallback_activity_ids("tôi muốn nghe nhạc", "bạn có thể thử playlist thư giãn")
    assert "ocean_sound" in ids


def test_align_reply_adds_ocean_when_generic():
    base = "Bạn có thể thử nghe nhạc nhẹ hoặc đi dạo."
    sug = [{"id": "ocean_sound", "title": "Âm sóng nhẹ", "description": "x"}]
    out = align_assistant_reply_with_suggestions(base, sug)
    assert "âm sóng" in out.lower()
    assert base in out


def test_align_reply_skips_ocean_when_already_aligned():
    base = "Bạn có thể mở âm sóng nhẹ trong app."
    sug = [{"id": "ocean_sound", "title": "Âm sóng nhẹ", "description": "x"}]
    assert align_assistant_reply_with_suggestions(base, sug) == base.strip()


    text = '```json\n{"activity_ids": ["ocean_sound", "breathing_box"]}\n```'
    assert _parse_activity_id_list(text) == ["ocean_sound", "breathing_box"]


def test_parse_activity_truncates_to_allowed_and_max_two():
    raw = '{"ids": ["ocean_sound", "breathing_box", "invalid", "ocean_sound"]}'
    assert _parse_activity_id_list(raw) == ["ocean_sound", "breathing_box"]


@pytest.mark.asyncio
async def test_high_risk_skips_suggestions():
    out = await detect_suggested_activities_llm(
        user_input="x",
        assistant_reply="y",
        risk_level="high",
        provider="openai",
    )
    assert out == []
