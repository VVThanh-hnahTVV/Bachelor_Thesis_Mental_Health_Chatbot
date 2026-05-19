from app.graph.nodes.response_filter import _safe_fallback


def test_fallback_next_step_after_exercise_vi():
    state = {
        "user_input": "làm xong rồi sao nữa",
        "history": [],
    }
    fb = _safe_fallback(state)
    assert "chia sẻ thêm" not in fb.lower()
    assert "nặng" in fb.lower() or "bước" in fb.lower()


def test_fallback_default_vi():
    state = {"user_input": "tôi buồn", "history": []}
    fb = _safe_fallback(state)
    assert "chia sẻ" in fb.lower()
