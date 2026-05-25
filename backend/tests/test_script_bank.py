from app.graph.script_bank import (
    _load_scenarios,
    match_scenario,
    render_template,
    should_use_script_for_turn,
)
from app.screening.phq import score_phq as phq_score


def test_match_greeting():
    sc = match_scenario("xin chào bạn", intent="casual")
    assert sc is not None
    assert sc.id == "greeting"


def test_match_objection_only():
    sc = match_scenario("random", objection_detected=True)
    assert sc is not None
    assert sc.id == "objection_apology"


def test_render_template_vi():
    sc = match_scenario("bạn là ai", intent="casual")
    assert sc is not None
    text = render_template(sc, "vi")
    assert "Luna" in text


def test_phq_score():
    assert phq_score([0, 1, 2, 3]) == 6


def test_mild_distress_removed():
    ids = {s.id for s in _load_scenarios()}
    assert "mild_distress" not in ids


def test_topic_script_skipped_after_first_user_turn():
    sc = match_scenario(
        "My lover and I had a break up",
        intent="relationship_stress",
    )
    assert sc is not None
    assert sc.id == "relationship_stress"
    history = [
        {"role": "user", "content": "hi"},
        {"role": "assistant", "content": "Hello"},
    ]
    assert not should_use_script_for_turn(sc, history)


def test_greeting_script_skipped_after_assistant_reply():
    sc = match_scenario("xin chào bạn", intent="casual")
    assert sc is not None
    history = [
        {"role": "user", "content": "fdsaf"},
        {"role": "assistant", "content": "I'm here for feelings and wellbeing."},
    ]
    assert not should_use_script_for_turn(sc, history)


def test_capability_script_skipped_mid_conversation():
    sc = match_scenario("what can you help me", intent="casual")
    assert sc is not None
    history = [
        {"role": "user", "content": "fdsaf"},
        {"role": "assistant", "content": "I'm here for feelings and wellbeing."},
    ]
    assert not should_use_script_for_turn(sc, history)
