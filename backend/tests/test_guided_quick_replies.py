from app.graph.guided_quick_replies import ensure_three_quick_replies, guided_quick_replies


def test_guided_returns_three():
    opts = guided_quick_replies(
        lang="vi",
        strategy="stabilization",
        emotion="hopeless",
        intent="venting",
    )
    assert len(opts) == 3


def test_ensure_three_pads_from_partial():
    partial = [{"id": "1", "label": "A", "message": "Tin A"}]
    out = ensure_three_quick_replies(
        partial,
        lang="vi",
        strategy="reflective_listening",
        emotion="sadness",
        intent="venting",
    )
    assert len(out) == 3
    assert len({o["message"] for o in out}) == 3
