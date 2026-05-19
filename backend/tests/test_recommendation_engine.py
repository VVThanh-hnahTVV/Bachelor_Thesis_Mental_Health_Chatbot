from app.wellness.recommendation_engine import (
    RecommendationSignals,
    evaluate_recommendation,
    should_show_activity_micro_feedback,
)


def _signals(**kwargs) -> RecommendationSignals:
    base = {
        "user_input": "",
        "assistant_reply": "",
        "intent": "venting",
        "primary_emotion": "sadness",
        "emotion_intensity": 0.7,
        "therapy_strategy": "reflective_listening",
        "user_turn_count": 2,
        "risk_level": "low",
        "history": [],
    }
    base.update(kwargs)
    return RecommendationSignals(**base)


def test_early_venting_no_activity():
    d = evaluate_recommendation(_signals(user_input="Tôi thấy mệt mỏi quá"))
    assert not d.eligible
    assert d.reason == "early_venting_listen_first"


def test_turn2_greeting_no_activity():
    d = evaluate_recommendation(
        _signals(
            user_input="Xin chào",
            intent="casual",
            primary_emotion="neutral",
            emotion_intensity=0.3,
            user_turn_count=1,
        )
    )
    assert not d.eligible


def test_explicit_breathing_request():
    d = evaluate_recommendation(
        _signals(
            user_input="Cho tôi bài hít thở",
            user_turn_count=1,
        )
    )
    assert d.eligible
    assert d.activity_ids == ["breathing_box"]


def test_panic_grounding_after_enough_turns():
    d = evaluate_recommendation(
        _signals(
            user_input="Tim đập nhanh quá",
            intent="panic_support",
            primary_emotion="anxiety",
            emotion_intensity=0.8,
            therapy_strategy="grounding",
            user_turn_count=4,
        )
    )
    assert d.eligible
    assert "breathing_box" in d.activity_ids


def test_sustained_stress_low_mood():
    history = [
        {"role": "user", "content": "Mệt quá"},
        {"role": "assistant", "content": "..."},
        {"role": "user", "content": "Không ngủ được"},
        {"role": "assistant", "content": "..."},
        {"role": "user", "content": "Chán quá"},
    ]
    d = evaluate_recommendation(
        _signals(
            user_input="Chán quá",
            primary_emotion="sadness",
            user_turn_count=6,
            history=history,
            turns_since_last_suggestion=5,
        )
    )
    assert d.eligible
    assert d.activity_ids == ["ocean_sound"]


def test_cooldown_blocks_repeat():
    d = evaluate_recommendation(
        _signals(
            user_input="Tôi stress",
            intent="seeking_advice",
            primary_emotion="anxiety",
            emotion_intensity=0.8,
            therapy_strategy="CBT",
            user_turn_count=6,
            turns_since_last_suggestion=1,
        )
    )
    assert not d.eligible
    assert d.reason == "cooldown"


def test_micro_feedback_not_on_first_vent():
    assert not should_show_activity_micro_feedback(
        user_turn_count=2,
        intent="venting",
        therapy_strategy="reflective_listening",
        reply="Có vẻ bạn đang mệt. Bạn muốn chia sẻ thêm không?",
        suggested_activities=[{"id": "ocean_sound"}],
        objection_detected=False,
    )


def test_micro_feedback_skipped_when_activity_buttons_shown():
    assert not should_show_activity_micro_feedback(
        user_turn_count=6,
        intent="seeking_advice",
        therapy_strategy="CBT",
        reply="A" * 120,
        suggested_activities=[{"id": "breathing_box"}],
        objection_detected=False,
    )


def test_micro_feedback_on_substantive_reply_without_buttons():
    assert should_show_activity_micro_feedback(
        user_turn_count=6,
        intent="seeking_advice",
        therapy_strategy="CBT",
        reply="A" * 120,
        suggested_activities=[],
        objection_detected=False,
    )
