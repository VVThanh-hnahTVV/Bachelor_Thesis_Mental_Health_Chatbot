from app.graph.nodes.response_generator import (
    build_system_prompt,
    detect_language,
    is_meta_conversation,
    _sanitize,
)


def test_detect_language_vietnamese():
    assert detect_language("Chào bạn, hôm nay tôi cảm thấy buồn") == "vi"


def test_detect_language_english():
    assert detect_language("I feel anxious today") == "en"


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
    assert "Natural conversation" in prompt
    assert "Vietnamese only" in prompt


def test_sanitize_strips_english_bleed_for_vietnamese():
    raw = (
        "Tôi có thể lắng nghe bạn.\n"
        "Does this relate to what you're going through?"
    )
    out = _sanitize(raw, reply_language="vi")
    assert "Does this relate" not in out
    assert "lắng nghe" in out
