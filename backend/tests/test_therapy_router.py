import pytest

from app.graph.nodes.therapy_router import (
    has_relationship_context,
    is_post_stabilization_followup,
    node_therapy_router,
    resolve_hopeless_strategy,
)


def test_hopeless_first_turn_stabilization():
    state = {
        "primary_emotion": "hopeless",
        "intent": "venting",
        "user_input": "tôi tuyệt vọng",
        "therapy_flags": {},
        "history": [],
    }
    assert resolve_hopeless_strategy(state) == "stabilization"


def test_hopeless_after_stabilization_post_stab():
    state = {
        "primary_emotion": "hopeless",
        "intent": "venting",
        "user_input": "làm xong rồi sao nữa",
        "therapy_flags": {"stabilization_turn": 3, "last_strategy": "stabilization"},
        "history": [{"role": "user", "content": "người mình yêu không yêu mình"}],
    }
    assert resolve_hopeless_strategy(state) == "post_stabilization"


def test_relationship_context_detected():
    state = {
        "user_input": "chán",
        "history": [{"role": "user", "content": "người mình yêu không yêu mình"}],
    }
    assert has_relationship_context(state) is True


def test_post_stabilization_followup_markers():
    assert is_post_stabilization_followup("làm xong rồi sao nữa") is True
    assert is_post_stabilization_followup("hello") is False


@pytest.mark.asyncio
async def test_router_skips_stabilization_repeat():
    out = await node_therapy_router(
        {
            "primary_emotion": "hopeless",
            "intent": "venting",
            "user_input": "chán",
            "therapy_flags": {"stabilization_turn": 2, "last_strategy": "stabilization"},
            "history": [],
            "objection_detected": False,
        }
    )
    assert out["therapy_strategy"] in ("post_stabilization", "CBT", "reflective_listening")
    assert out["therapy_strategy"] != "stabilization"
