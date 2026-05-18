from app.graph.script_bank import match_scenario, render_template
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
