import pytest

from app.graph.nodes.therapy_router import (
    has_physical_distress,
    has_relationship_context,
    is_post_stabilization_followup,
    is_sustained_emotional_sharing_lane,
    node_therapy_router,
    resolve_hopeless_strategy,
    resolve_venting_regulation_strategy,
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


def test_physical_distress_detected():
    assert has_physical_distress("I feel a tightness in my chest and a lump in my throat")
    assert has_physical_distress("mình thấy thắt ngực và nghẹn họng")
    assert has_physical_distress("I have a knot in my stomach")
    assert not has_physical_distress("I miss her so much")


def test_sustained_emotional_sharing_lane():
    state = {"history": [], "user_input": "hi"}
    assert is_sustained_emotional_sharing_lane("venting", state) is True
    assert is_sustained_emotional_sharing_lane("journaling", state) is True
    assert is_sustained_emotional_sharing_lane("general_health", state) is False
    assert is_sustained_emotional_sharing_lane(
        "general_health",
        {"history": [{"role": "user", "content": "we broke up"}], "user_input": "still hurts"},
    ) is True


def test_venting_physical_symptoms_routes_to_grounding():
    state = {
        "user_input": "I feel a tightness in my chest and a lump in my throat",
        "history": [
            {"role": "user", "content": "My boss is unbearable"},
            {"role": "assistant", "content": "That sounds draining."},
        ],
        "therapy_flags": {"reflective_listening_turns": 2, "last_strategy": "reflective_listening"},
    }
    assert resolve_venting_regulation_strategy(state) == "grounding"


def test_venting_after_reflective_turns_offers_grounding():
    state = {
        "user_input": "I keep replaying what they said in the meeting",
        "history": [{"role": "user", "content": "x"}] * 3,
        "therapy_flags": {"reflective_listening_turns": 2, "last_strategy": "reflective_listening"},
    }
    assert resolve_venting_regulation_strategy(state) == "grounding"


def test_hopeless_after_stabilization_journaling_routes_post_stabilization():
    state = {
        "primary_emotion": "hopeless",
        "intent": "journaling",
        "user_input": "làm xong rồi sao nữa",
        "therapy_flags": {"stabilization_turn": 3, "last_strategy": "stabilization"},
        "history": [{"role": "user", "content": "nothing feels worth writing"}],
    }
    assert resolve_hopeless_strategy(state) == "post_stabilization"


def test_hopeless_after_stabilization_general_health_routes_cbt():
    state = {
        "primary_emotion": "hopeless",
        "intent": "general_health",
        "user_input": "làm xong rồi sao nữa",
        "therapy_flags": {"stabilization_turn": 3, "last_strategy": "stabilization"},
        "history": [{"role": "user", "content": "how many hours of sleep do teens need"}],
    }
    assert resolve_hopeless_strategy(state) == "CBT"


@pytest.mark.asyncio
async def test_router_somatic_cue_returns_grounding_for_venting():
    out = await node_therapy_router(
        {
            "primary_emotion": "sadness",
            "intent": "venting",
            "user_input": "I feel a knot in my stomach every morning before work",
            "therapy_flags": {},
            "history": [],
            "objection_detected": False,
        }
    )
    assert out["therapy_strategy"] == "grounding"


@pytest.mark.asyncio
async def test_router_psychoeducation_does_not_force_grounding_on_body_words():
    out = await node_therapy_router(
        {
            "primary_emotion": "neutral",
            "intent": "psychoeducation",
            "user_input": "Why do people describe a lump in the throat when anxious?",
            "therapy_flags": {},
            "history": [],
            "objection_detected": False,
        }
    )
    assert out["therapy_strategy"] != "grounding"
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
