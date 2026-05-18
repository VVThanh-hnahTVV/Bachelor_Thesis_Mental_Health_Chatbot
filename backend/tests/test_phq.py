from app.screening.phq import get_questions, interpret_phq2, score_phq


def test_score_phq():
    assert score_phq([1, 2]) == 3


def test_phq2_questions():
    assert len(get_questions("phq2")) == 2


def test_interpret():
    assert "theo dõi" in interpret_phq2(4).lower() or "chuyên gia" in interpret_phq2(4).lower()
