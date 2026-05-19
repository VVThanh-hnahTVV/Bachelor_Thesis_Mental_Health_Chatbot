from app.graph.workflow import route_after_emotion_intent


def test_route_after_emotion_intent_off_topic():
    assert route_after_emotion_intent({"intent": "off_topic"}) == "off_topic_reply"


def test_route_after_emotion_intent_health_or_casual():
    assert route_after_emotion_intent({"intent": "casual"}) == "memory_retrieval"
    assert route_after_emotion_intent({"intent": "panic_support"}) == "memory_retrieval"
