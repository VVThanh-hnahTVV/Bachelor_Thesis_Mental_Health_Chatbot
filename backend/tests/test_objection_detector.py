from app.graph.nodes.objection_detector import detect_objection, node_objection_detector
import pytest


def test_detect_refusal_breathing():
    detected, typ = detect_objection("đừng bảo tôi thở nữa")
    assert detected is True
    assert typ == "refusal"


def test_detect_misunderstanding():
    detected, typ = detect_objection("Bạn hiểu sai rồi")
    assert detected is True
    assert typ == "misunderstanding"


def test_detect_repetition():
    detected, typ = detect_objection("Đừng lặp lại nữa")
    assert detected is True
    assert typ == "repetition"


def test_no_objection():
    detected, typ = detect_objection("Hôm nay tôi cảm thấy buồn")
    assert detected is False
    assert typ is None


@pytest.mark.asyncio
async def test_node_sets_strategy():
    out = await node_objection_detector({"user_input": "sai rồi", "metadata": {}})
    assert out["objection_detected"] is True
    assert out["therapy_strategy"] == "reflective_listening"
