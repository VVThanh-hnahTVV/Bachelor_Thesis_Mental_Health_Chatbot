import pytest

from app.graph.safety_engine import crisis_reply_for_language, run_safety_engine


@pytest.mark.asyncio
async def test_safety_engine_keyword_crisis_high():
    out = await run_safety_engine("I want to die", [], "openai")
    assert out["risk_level"] == "high"
    assert out["emergency_mode"] is True
    assert "keyword_crisis" in out["triggers"]


@pytest.mark.asyncio
async def test_safety_engine_suspicious_failure_is_conservative(monkeypatch):
    async def fail(*_args, **_kwargs):
        raise RuntimeError("provider down")

    monkeypatch.setattr("app.graph.safety_engine.get_chat_model", lambda _provider: object())
    monkeypatch.setattr("app.graph.safety_engine.invoke_with_fallback", fail)

    out = await run_safety_engine("Everything feels hopeless", [], "openai")
    assert out["risk_level"] == "medium"
    assert out["emergency_mode"] is False
    assert "llm_failure" in out["triggers"]


@pytest.mark.asyncio
async def test_safety_engine_low_risk_fast_path():
    out = await run_safety_engine("hello", [], "openai")
    assert out["risk_level"] == "low"
    assert out["emergency_mode"] is False


def test_crisis_reply_matches_language():
    en_reply, en_choices = crisis_reply_for_language("en")
    vi_reply, vi_choices = crisis_reply_for_language("vi")
    assert "988" in en_reply
    assert "115" in vi_reply
    assert en_choices[0].startswith("I want")
    assert vi_choices[0].startswith("Tôi")
