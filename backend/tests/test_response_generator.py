import pytest

from app.graph.nodes.response_generator import (
    build_system_prompt,
    detect_language,
    is_meta_conversation,
    node_response_generator,
    _sanitize,
)


def test_detect_language_vietnamese():
    assert detect_language("Chào bạn, hôm nay tôi cảm thấy buồn") == "vi"


def test_detect_language_english():
    assert detect_language("I feel anxious today") == "en"


def test_detect_language_prefers_latest_message_over_history():
    history = [{"role": "user", "content": "Mình thấy khá mệt"}]
    assert detect_language("Do you know me", history) == "en"


def test_is_meta_conversation():
    assert is_meta_conversation("Bạn có thể giúp gì cho tôi")
    assert is_meta_conversation("Bạn là ai")
    assert not is_meta_conversation("Tôi không ngủ được ba đêm rồi")


def test_build_system_prompt_uses_casual_for_meta():
    prompt = build_system_prompt(
        "psychoeducation",
        "general_health",
        [],
        {},
        user_input="Bạn có thể giúp gì cho tôi",
        reply_language="vi",
    )
    assert "Warm greeting or small talk" in prompt
    assert "Vietnamese only" in prompt


def test_build_system_prompt_uses_casual_followup_mid_chat():
    history = [
        {"role": "user", "content": "fdsaf"},
        {"role": "assistant", "content": "I'm here for feelings."},
    ]
    prompt = build_system_prompt(
        "reflective_listening",
        "casual",
        [],
        {},
        user_input="What can you help me",
        reply_language="en",
        history=history,
    )
    assert "Explain how you can help (mid-conversation)" in prompt
    assert "Continuation (not the opening message)" in prompt
    assert "Warm greeting or small talk" not in prompt


def test_sanitize_strips_english_bleed_for_vietnamese():
    raw = (
        "Tôi có thể lắng nghe bạn.\n"
        "Does this relate to what you're going through?"
    )
    out = _sanitize(raw, reply_language="vi")
    assert "Does this relate" not in out
    assert "lắng nghe" in out


def test_build_system_prompt_includes_personalization_context():
    prompt = build_system_prompt(
        "reflective_listening",
        "general_health",
        [],
        {
            "mood_trend": "declining",
            "recent_mood_notes": ["Ngu khong sau"],
            "preferred_tone": "gentle",
            "user_display_name": "An",
        },
        user_input="Hom nay toi met",
        reply_language="vi",
    )
    assert "Recent mood trend: declining" in prompt
    assert "Recent mood highlights: Ngu khong sau" in prompt
    assert "User display name: An" in prompt


def test_build_system_prompt_adds_rag_relevance_rule():
    prompt = build_system_prompt(
        "psychoeducation",
        "general_health",
        ["Sleep routines help reduce insomnia."],
        {},
        user_input="I cannot sleep",
        reply_language="en",
    )
    assert "Use these only if they directly help" in prompt
    assert "Sleep routines" in prompt

@pytest.mark.asyncio
async def test_known_user_query_uses_display_name_vi():
    out = await node_response_generator(
        {
            "user_input": "Bạn biết mình là ai không",
            "history": [],
            "provider": "openai",
            "long_term_context": {"user_display_name": "Viet"},
        }
    )
    assert "Viet" in out["final_reply"]


@pytest.mark.asyncio
async def test_known_user_query_uses_display_name_en():
    out = await node_response_generator(
        {
            "user_input": "Do you know me",
            "history": [{"role": "user", "content": "Xin chào"}],
            "provider": "openai",
            "long_term_context": {"user_display_name": "Viet"},
        }
    )
    assert "Viet" in out["final_reply"]
    assert out["final_reply"].lower().startswith("yes")
