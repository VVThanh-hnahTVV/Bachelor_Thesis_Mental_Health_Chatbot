from app.graph.conversation_ui import (
    is_learn_exploration,
    is_substantive_reply,
    should_show_micro_feedback,
    should_skip_wellness_suggestions,
)


def test_learn_exploration_skips_wellness():
    assert is_learn_exploration("Tôi muốn tìm hiểu về sức khỏe tâm lý")
    assert should_skip_wellness_suggestions(
        user_input="Tôi muốn tìm hiểu về sức khỏe tâm lý",
        intent="general_health",
        therapy_strategy="psychoeducation",
        reply="Bạn muốn tìm hiểu — mình sẽ chia sẻ ngắn gọn.",
    )


def test_short_clarify_not_substantive():
    assert not is_substantive_reply("Bạn quan tâm chủ đề nào — lo âu hay giấc ngủ?")


def test_no_feedback_on_learn_turn():
    assert not should_show_micro_feedback(
        message_type="normal",
        intent="general_health",
        user_input="Tôi muốn tìm hiểu về sức khỏe tâm lý",
        therapy_strategy="psychoeducation",
        reply="Bạn muốn tìm hiểu — mình sẽ chia sẻ ngắn gọn.",
        objection_detected=False,
        chat_blocked=False,
    )
