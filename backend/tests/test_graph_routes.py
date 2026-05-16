from app.graph.workflow import route_after_risk, route_after_generate
from langgraph.graph import END


def test_route_after_risk_high():
    assert route_after_risk({"risk_level": "high"}) == "crisis"


def test_route_after_risk_low():
    assert route_after_risk({"risk_level": "low"}) == "generate"


def test_route_after_generate_coping():
    assert route_after_generate({"risk_level": "low", "include_coping": True}) == "coping"


def test_route_after_generate_end():
    assert route_after_generate({"risk_level": "low", "include_coping": False}) == END
