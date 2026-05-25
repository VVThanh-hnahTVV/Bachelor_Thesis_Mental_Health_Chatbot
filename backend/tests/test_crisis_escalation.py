import pytest

from app.graph.crisis_escalation import (
    CRISIS_CHIP_PREFIX,
    CrisisStage,
    advance_crisis_escalation,
    chips_for_stage,
    parse_crisis_chip_id,
    resolve_crisis_stage,
    safety_result_for_chip,
    strategy_for_chip,
)
from app.graph.safety_engine import _keyword_risk, run_safety_engine


def _safety(**kwargs):
    base = {
        "risk_level": "low",
        "confidence": 0.9,
        "triggers": [],
        "emergency_mode": False,
        "suggested_stage": "none",
    }
    base.update(kwargs)
    return base  # type: ignore[return-value]


def test_parse_crisis_chip_id_prefix():
    assert parse_crisis_chip_id(f"{CRISIS_CHIP_PREFIX}crisis:ack_safety_concern") == "crisis:ack_safety_concern"


def test_resolve_stage_first_high_goes_concern():
    stage = resolve_crisis_stage(
        escalation={"crisis_stage": "none", "high_risk_turns": 0, "user_acknowledged_risk": False},
        safety=_safety(risk_level="high", suggested_stage="concern"),
        user_message="I want to die",
    )
    assert stage == CrisisStage.CONCERN


def test_strategy_for_share_more_chip():
    assert strategy_for_chip("crisis:share_more") == "crisis_listen"
    assert strategy_for_chip("crisis:breathing_light") == "crisis_grounding"


def test_chip_ack_safety_moves_to_confirm():
    stage = resolve_crisis_stage(
        escalation={"crisis_stage": "concern", "high_risk_turns": 1, "user_acknowledged_risk": False},
        safety=_safety(risk_level="high", suggested_stage="concern"),
        user_message=f"{CRISIS_CHIP_PREFIX}crisis:ack_safety_concern",
    )
    assert stage == CrisisStage.CONFIRM


def test_chip_confirm_self_harm_moves_to_sos():
    stage = resolve_crisis_stage(
        escalation={"crisis_stage": "confirm", "high_risk_turns": 2, "user_acknowledged_risk": False},
        safety=_safety(risk_level="high", emergency_mode=True, suggested_stage="sos"),
        user_message=f"{CRISIS_CHIP_PREFIX}crisis:confirm_self_harm",
    )
    assert stage == CrisisStage.SOS


def test_imminent_keyword_skips_to_sos():
    kw = _keyword_risk("tối nay tôi sẽ tự tử")
    assert kw is not None
    assert kw["emergency_mode"] is True
    assert kw["suggested_stage"] == "sos"


def test_explicit_keyword_suggests_concern_not_emergency():
    kw = _keyword_risk("tôi muốn chết")
    assert kw is not None
    assert kw["emergency_mode"] is False
    assert kw["suggested_stage"] == "concern"


def test_deescalation_chip_lowers_safety_risk():
    out = safety_result_for_chip("crisis:share_more")
    assert out is not None
    assert out["risk_level"] == "medium"
    assert out["emergency_mode"] is False


def test_chips_concern_no_hotline_wording():
    vi = chips_for_stage(CrisisStage.CONCERN, "vi")
    labels = " ".join(c["label"] for c in vi)
    assert "115" not in labels
    assert "1800" not in labels


@pytest.mark.asyncio
async def test_advance_escalation_persists_stage():
    class FakeRedis:
        def __init__(self):
            self.store: dict[str, str] = {}

        async def get(self, key):
            return self.store.get(key)

        async def set(self, key, value, ex=None):
            self.store[key] = value

    redis = FakeRedis()
    safety = _safety(risk_level="high", suggested_stage="concern")
    stage, state = await advance_crisis_escalation(
        redis, "sess-1", safety=safety, user_message="I want to die"
    )
    assert stage == CrisisStage.CONCERN
    assert state["crisis_stage"] == "concern"
    assert state["high_risk_turns"] == 1
