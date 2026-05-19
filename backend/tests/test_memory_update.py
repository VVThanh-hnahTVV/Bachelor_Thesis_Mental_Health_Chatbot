import pytest
from langchain_core.messages import AIMessage

from app.graph.nodes.memory_update import run_memory_update


@pytest.mark.asyncio
async def test_memory_update_deduplicates_profile_lists(monkeypatch):
    saved: dict[str, object] = {}

    async def fake_invoke(*_args, **_kwargs):
        return AIMessage(
            content='{"new_stressors":["work","Work"],"coping_pref":"walk","tone_pref":"gentle"}'
        )

    async def fake_get_user_profile(_db, _session_id):
        return {
            "recurring_stressors": ["Work"],
            "coping_preferences": ["journal"],
        }

    async def fake_upsert(_db, session_id, updates):
        saved["session_id"] = session_id
        saved["updates"] = updates

    monkeypatch.setattr("app.graph.nodes.memory_update.get_chat_model", lambda _provider: object())
    monkeypatch.setattr("app.graph.nodes.memory_update.invoke_with_fallback", fake_invoke)
    monkeypatch.setattr("app.db.repository.get_user_profile", fake_get_user_profile)
    monkeypatch.setattr("app.db.repository.upsert_user_profile", fake_upsert)

    await run_memory_update(object(), "session-12345678", "user", "assistant", "openai")

    updates = saved["updates"]
    assert updates["recurring_stressors"] == ["Work"]
    assert updates["coping_preferences"] == ["journal", "walk"]
    assert updates["preferred_tone"] == "gentle"
